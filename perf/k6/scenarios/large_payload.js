import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.TARGET_URL || "http://host.docker.internal:8000";
const source = __ENV.SOURCE || "perf";
const tenant = __ENV.TENANT || "tenant-a";
const fanout = __ENV.FANOUT || "single";
const blobSize = Number(__ENV.PAYLOAD_BYTES || 262144);
const blob = "x".repeat(blobSize);

export const options = {
  vus: Number(__ENV.VUS || 8),
  duration: __ENV.DURATION || "3m",
  thresholds: {
    "http_req_failed{scenario:large_payload}": ["rate<0.03"],
    "http_req_duration{scenario:large_payload}": ["p(95)<1500", "p(99)<3000"],
  },
};

export default function () {
  const payload = JSON.stringify({
    tenant,
    event: "large_payload_profile",
    order_id: `${__VU}-${__ITER}`,
    notes: blob,
  });

  const res = http.post(`${baseUrl}/webhooks/${source}`, payload, {
    tags: {
      scenario: "large_payload",
      tenant,
      payload: "large",
      fanout,
    },
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `large-${__VU}-${__ITER}`,
    },
  });

  check(res, { "status is 2xx": (r) => r.status >= 200 && r.status < 300 });
  sleep(0.2);
}
