import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "2m",
  thresholds: {
    "http_req_failed{scenario:baseline}": ["rate<0.01"],
    "http_req_duration{scenario:baseline}": ["p(95)<350", "p(99)<800"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "baseline",
    order_id: `${__VU}-${__ITER}`,
    amount: 100 + (__ITER % 10),
  });

  const url = `${baseUrl}/webhooks/${source}`;
  const params = {
    tags: {
      scenario: "baseline",
      tenant,
      payload: "small",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `baseline-${__VU}-${__ITER}`,
    },
  };

  const res = http.post(url, payload, params);
  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });
  sleep(0.2);
}
