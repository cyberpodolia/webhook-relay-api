import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";

export const options = {
  stages: [
    { duration: "30s", target: 20 },
    { duration: "30s", target: 120 },
    { duration: "30s", target: 120 },
    { duration: "30s", target: 20 },
  ],
  thresholds: {
    "http_req_failed{scenario:spike}": ["rate<0.03"],
    "http_req_duration{scenario:spike}": ["p(95)<800", "p(99)<1500"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "spike",
    order_id: `${__VU}-${__ITER}`,
    amount: 100 + (__ITER % 10),
  });

  const url = `${baseUrl}/webhooks/${source}`;
  const params = {
    tags: {
      scenario: "spike",
      tenant,
      payload: "small",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `spike-${__VU}-${__ITER}`,
    },
  };

  const res = http.post(url, payload, params);
  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });
  sleep(0.1);
}
