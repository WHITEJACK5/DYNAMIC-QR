// k6 load test for the /r/<code> redirect path (Phase 5d).
//
// Directive: "Add load testing (k6 or Locust) for the /r/<code> redirect
// path specifically — this is the path real users hit and it must be proven
// fast under load."
//
// This is the hot path: every physical QR code in the world points here, so
// it is the only endpoint whose latency is visible to the public.
//
//   k6 run -e BASE_URL=http://127.0.0.1:8000 -e CODE=abc12345 loadtests/redirect.js
//
// The thresholds below are the contract. They are set from the latency this
// service actually needs to feel instant, not from whatever the run
// happened to produce: a redirect that p95 exceeds 300ms is noticeable on a
// phone camera, and 1% errors is not an acceptable redirect failure rate.
import http from "k6/http";
import { check } from "k6";
import { Trend, Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const CODE = __ENV.CODE || "abc12345";

// Dedicated metrics so the redirect can be tracked separately from the rest
// of the API if this script is ever extended.
const redirectDuration = new Trend("nare_redirect_duration", true);
const redirectFailed = new Rate("nare_redirect_failed");

export const options = {
  scenarios: {
    // A steady ramp that settles on a sustained rate, which is a better
    // model of real scanning traffic than a single spike.
    //
    // QUICK=1 gives a short, light profile for CI and laptop runs, where a
    // 100 req/s ramp exhausts the box and takes the app with it. The full
    // profile is the release-gate run.
    redirect_sustained: __ENV.QUICK === "1"
      ? {
          executor: "ramping-arrival-rate",
          startRate: 5,
          timeUnit: "1s",
          preAllocatedVUs: 10,
          maxVUs: 50,
          stages: [
            { target: 20, duration: "5s" },
            { target: 25, duration: "10s" },
            { target: 0, duration: "3s" },
          ],
        }
      : {
          executor: "ramping-arrival-rate",
          startRate: 10,
          timeUnit: "1s",
          preAllocatedVUs: 50,
          maxVUs: 300,
          stages: [
            { target: 50, duration: "30s" },
            { target: 100, duration: "30s" },
            { target: 100, duration: "1m" },
            { target: 0, duration: "15s" },
          ],
        },
  },
  thresholds: {
    "http_req_failed": ["rate<0.01"],
    "http_req_duration": ["p(95)<300", "p(99)<800"],
    checks: ["rate>0.99"],
    nare_redirect_duration: ["p(95)<300"],
    nare_redirect_failed: ["rate<0.01"],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/r/${CODE}`, {
    headers: {
      // A real scanner sends a mobile UA and no cookies; sending one would
      // make the test easier than reality by skipping device detection.
      "User-Agent":
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) " +
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    },
    tags: { path: "redirect" },
    // Do NOT follow the 302.
    //
    // This is the whole point of testing a redirect endpoint. k6 follows
    // redirects by default, so with this left on, half the requests in the
    // run were the *destination* host — and when the destination is a public
    // URL the run measures a third party's latency, or fails on it. We are
    // measuring the 302 this service returns, nothing else.
    redirects: 0,
  });

  // A QR redirect is a 30x, not a 200 with an HTML page.
  const isRedirect = res.status === 302 || res.status === 301 ||
    res.status === 307 || res.status === 308;
  const ok = check(res, {
    "status is a redirect": () => isRedirect,
    "has a Location header": () => !!res.headers.Location,
    "not an error": () => res.status < 400,
  });

  redirectDuration.add(res.timings.duration);
  redirectFailed.add(!ok);
}
