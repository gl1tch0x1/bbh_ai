"""
sandbox/primitives/http_proxy.py — HTTP Request Intercept & Replay Primitive

Provides agents with the ability to intercept, inspect, modify, and replay
raw HTTP requests — equivalent to Burp Suite's Repeater, purely in Python.
Uses httpx for async HTTP, supports custom headers, bodies, and TLS bypass.
"""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_MAX_TIMEOUT = 60


class HttpProxyPrimitive:
    """
    Intercept and replay HTTP requests with full control over every header
    and body parameter. Used by exploit agents for manual verification and
    payload injection outside of automated tool wrappers.
    """

    def __init__(self, verify_ssl: bool = False):
        """
        Args:
            verify_ssl: Whether to verify TLS certificates. Default False
                        because bug-bounty targets often have self-signed certs.
        """
        self.verify_ssl = verify_ssl

    def intercept(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        follow_redirects: bool = False,
    ) -> Dict[str, Any]:
        """
        Send an HTTP request and return the full response for inspection.

        Returns:
            {
                "success":          bool,
                "status_code":      int,
                "headers":          dict,
                "body":             str,
                "content_length":   int,
                "elapsed_ms":       float,
                "final_url":        str,
            }
        """
        timeout = min(int(timeout), _MAX_TIMEOUT)
        logger.info(f"[Proxy] {method.upper()} {url}")

        try:
            with httpx.Client(
                verify=self.verify_ssl,
                follow_redirects=follow_redirects,
                timeout=timeout,
            ) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers or {},
                    content=body if isinstance(body, (bytes, str)) else None,
                    json=body if isinstance(body, dict) else None,
                    params=params,
                )
            return {
                "success":        True,
                "status_code":    response.status_code,
                "headers":        dict(response.headers),
                "body":           response.text,
                "content_length": len(response.content),
                "elapsed_ms":     response.elapsed.total_seconds() * 1000,
                "final_url":      str(response.url),
            }
        except httpx.TimeoutException:
            return {
                "success":     False,
                "error":       f"Request timed out after {timeout}s",
                "status_code": 0,
            }
        except Exception as exc:
            logger.error(f"[Proxy] Request failed: {exc}")
            return {
                "success":     False,
                "error":       str(exc),
                "status_code": 0,
            }

    def replay(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replay a previously captured request dict (from intercept output or
        manual specification). Allows agents to tweak specific fields and
        re-send for comparative analysis.
        """
        return self.intercept(
            url=request_dict.get("url", ""),
            method=request_dict.get("method", "GET"),
            headers=request_dict.get("headers"),
            body=request_dict.get("body"),
            params=request_dict.get("params"),
            timeout=request_dict.get("timeout", 30),
            follow_redirects=request_dict.get("follow_redirects", False),
        )

    def fuzz(
        self,
        url: str,
        method: str,
        payloads: list,
        param: str = "inject",
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
    ) -> list:
        """
        Send multiple requests with different payloads in the same parameter
        and return results for differential analysis.

        Returns a list of result dicts, one per payload.
        """
        results = []
        for payload in payloads:
            if method.upper() == "GET":
                result = self.intercept(
                    url=url,
                    method="GET",
                    params={param: payload},
                    headers=headers,
                    timeout=timeout,
                )
            else:
                result = self.intercept(
                    url=url,
                    method=method,
                    body={param: payload},
                    headers=headers,
                    timeout=timeout,
                )
            result["payload"] = payload
            results.append(result)
        return results
