import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "4m",
  thresholds: {
    "http_req_failed{scenario:flaky_receivers}": ["rate<0.15"],
    "http_req_duration{scenario:flaky_receivers}": ["p(95)<1200", "p(99)<2500"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "flaky_receiver_profile",
    order_id: `${__VU}-${__ITER}`,
    amount: 100 + (__ITER % 10),
  });

  const res = http.post(`${baseUrl}/webhooks/${source}`, payload, {
    tags: {
      scenario: "flaky_receivers",
      tenant,
      payload: "small",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `flaky-${__VU}-${__ITER}`,
    },
  });

  check(res, { "status is 2xx": (r) => r.status >= 200 && r.status < 300 });
  sleep(0.1);
}
