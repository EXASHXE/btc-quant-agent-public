"""Offline Feishu-shaped cards. Provider compatibility needs separate validation."""

import base64
import hashlib
import hmac
import json


class Secret:
    """Inject a secret getter; neither the getter nor value enters repr/storage/logs."""

    def __init__(self, getter):
        self._getter = getter

    def __repr__(self):
        return "<Secret redacted>"

    def read(self):
        try:
            value = self._getter()
            if not isinstance(value, str) or not value.strip():
                raise ValueError
            return value
        except Exception:
            raise ValueError("secret injection unavailable or invalid") from None


def signature(timestamp, secret):
    key = (str(timestamp) + "\n" + secret).encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode("ascii")


def make_card(event, now, secret=None):
    # All upstream content is plain text; never interpret user data as card markup.
    kind = event["event_type"]
    lines = ["SYNTHETIC / TEST ONLY — 离线模拟，禁止据此交易",
             "状态：" + kind, "Episode: " + event["episode_id"],
             "Account: " + event["account_status"],
             "Provider acceptance ≠ human read / acknowledgement"]
    if kind == "SYSTEM_DEGRADED":
        lines += ["系统降级：" + event["reason"]]
    else:
        p = event["plan"]
        lines += [event["symbol"] + " " + event["side"],
                  "4H: " + event["regime_4h"]["value"],
                  "1H completed: " + str(event["setup_1h"]["completed"]),
                  "15m completed: " + str(event["confirmation_15m"]["completed"]),
                  "Entry area: " + json.dumps(p["entry_area"]),
                  "Hard stop: " + str(p["hard_stop"]),
                  "TP(s): " + json.dumps(p["take_profits"]),
                  "Planned after-cost R: " + str(p["after_cost_r"]),
                  "Model assumptions: " + json.dumps(p["model"], sort_keys=True),
                  "5–10 min human delay: " + json.dumps(event["human_delay"]),
                  "Candidate expiry UTC epoch: " + str(event["candidate_expires_at"]),
                  "Invalidation: " + json.dumps(event["invalidation"], sort_keys=True)]
    lines += ["Notification expiry UTC epoch: " + str(event["expires_at"]),
              "Dashboard: " + event["dashboard_url"]]
    result = {"msg_type": "interactive", "card": {
        "header": {"template": "orange", "title": {
            "tag": "plain_text", "content": "[SYNTHETIC TEST] " + kind}},
        "elements": [{"tag": "div", "text": {
            "tag": "plain_text", "content": "\n".join(lines)}}]}}
    if secret is not None:
        timestamp = str(int(now))
        result.update(timestamp=timestamp, sign=signature(timestamp, secret.read()))
    return result
