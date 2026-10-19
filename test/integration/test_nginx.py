"""Validate the Nginx files under the real nginx binary (no long-running container, no published ports)."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.integration

NGINX = REPO_ROOT / "docker" / "nginx"
IMAGE = "nginx:alpine"

SETUP = (
    "set -e; mkdir -p /ragflow/web/dist; "
    "cp /etc/nginx-test/nginx.conf /etc/nginx/nginx.conf; "
    "cp /etc/nginx-test/proxy.conf /etc/nginx/proxy.conf; "
    "rm -f /etc/nginx/conf.d/*.conf; "
    "cp /etc/nginx-test/{conf} /etc/nginx/conf.d/ragflow.conf; "
)


def nginx_t(conf: str, mount_certs: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "run", "--rm", "--name", f"devrag-nginx-t-{uuid.uuid4().hex[:8]}",
           "-v", f"{NGINX}:/etc/nginx-test:ro"]
    if mount_certs:
        cmd += ["-v", f"{NGINX / 'certs'}:/etc/nginx/certs:ro"]
    cmd += ["--entrypoint", "sh", IMAGE, "-c", SETUP.format(conf=conf) + "nginx -t"]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)


def test_nginx_t_http() -> None:
    proc = nginx_t("ragflow.conf", mount_certs=False)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "syntax is ok" in out
    assert "test is successful" in out


def test_nginx_t_https() -> None:
    gen = subprocess.run(["bash", str(REPO_ROOT / "scripts/gen_selfsigned.sh"), "--force"],
                         capture_output=True, text=True, check=False, timeout=60)
    assert gen.returncode == 0, gen.stderr
    proc = nginx_t("ragflow.https.conf", mount_certs=True)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "syntax is ok" in out
    assert "test is successful" in out


@pytest.mark.parametrize("directive", [
    "proxy_buffering off;", "proxy_http_version 1.1;", 'proxy_set_header Connection "";',
    "proxy_cache off;",
])
def test_proxy_conf_is_sse_safe(directive: str) -> None:
    assert directive in (NGINX / "proxy.conf").read_text(encoding="utf-8")


@pytest.mark.parametrize("location", ["^~ /api/ ", "^~ /v1/ ", "= /api/v1/mcp ", "^~ /api/v1/searchbots/ "])
def test_streaming_locations_keep_the_long_upstream_timeouts(location: str) -> None:
    """The timeouts moved from proxy.conf to the generated locations (WR-04): streaming routes stay at 3600 s."""
    conf = (NGINX / "ragflow.conf").read_text(encoding="utf-8")
    block = conf.split(f"location {location}{{", 1)[1].split("\n    }", 1)[0]
    assert "proxy_read_timeout 3600s;" in block and "proxy_send_timeout 3600s;" in block


def test_static_assertions() -> None:
    assert "text/event-stream" not in (NGINX / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_hide_header" not in (NGINX / "ragflow.conf").read_text(encoding="utf-8")
    assert "proxy_hide_header" not in (NGINX / "proxy.conf").read_text(encoding="utf-8")


# Nothing listens on 9380 in this container, so a body that Nginx lets through to Python would be a 502, never a 413.
OVERSIZE_PROBE = (
    "nginx; head -c 2097152 /dev/zero | tr '\\0' ' ' | "
    "curl -s -o /dev/null -w '%{{http_code}}' --retry 20 --retry-delay 0 --retry-max-time 8 --retry-connrefused "
    "-X POST -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1{path}"
)


@pytest.mark.parametrize("path", ["/api/v1/chats", "/api/v1/chats/0123456789abcdef0123456789abcdef", "/api/v1/chat/completions"])
def test_chat_families_refuse_a_2_mib_body_with_413_before_the_app(path: str) -> None:
    """Plan 05-08: the chat families carry the 1m JSON limit, so the 1024m catch-all never sees these bodies."""
    cmd = ["docker", "run", "--rm", "--name", f"devrag-nginx-413-{uuid.uuid4().hex[:8]}", "-v", f"{NGINX}:/etc/nginx-test:ro",
           "--entrypoint", "sh", IMAGE, "-c", SETUP.format(conf="ragflow.conf") + OVERSIZE_PROBE.format(path=path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().endswith("413"), proc.stdout + proc.stderr
