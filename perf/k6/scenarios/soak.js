import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";

export const options = {
  vus: Number(__ENV.VUS || 25),
  duration: __ENV.DURATION || "15m",
  thresholds: {
    "http_req_failed{scenario:soak}": ["rate<0.02"],
    "http_req_duration{scenario:soak}": ["p(95)<500", "p(99)<1200"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "soak",
    order_id: `${__VU}-${__ITER}`,
    amount: 100 + (__ITER % 100),
  });

  const res = http.post(`${baseUrl}/webhooks/${source}`, payload, {
    tags: {
      scenario: "soak",
      tenant,
      payload: "small",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `soak-${__VU}-${__ITER}`,
    },
  });

  check(res, { "status is 2xx": (r) => r.status >= 200 && r.status < 300 });
  sleep(0.15);
}
