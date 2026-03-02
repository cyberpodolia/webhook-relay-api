import http from "k6/http";
import { check } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    "http_req_failed{scenario:sanity}": ["rate<0.01"],
    "http_req_duration{scenario:sanity}": ["p(95)<500", "p(99)<1000"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "sanity",
    amount: 100,
  });

  const url = `${baseUrl}/webhooks/${source}`;
  const params = {
    tags: {
      scenario: "sanity",
      tenant,
      payload: "small",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `sanity-${__VU}-${__ITER}`,
    },
  };

  const res = http.post(url, payload, params);
  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });
}
