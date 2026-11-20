# -*- coding: utf-8 -*-
# Copyright: (c) 2026, Lenny Shirley
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Minimal JSON HTTP client built on ansible's ``open_url`` (no third party deps)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json

from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.urls import open_url


class ApiError(Exception):
    """Raised for transport failures, non-2xx responses, and API level errors."""

    def __init__(self, message, status=None, url=None):
        super(ApiError, self).__init__(message)
        self.status = status
        self.url = url


class HttpClient:
    """Tiny session-like wrapper: base URL, default headers, cookies, TLS settings."""

    def __init__(self, base_url, headers=None, validate_certs=True, timeout=30,
                 url_username=None, url_password=None, force_basic_auth=False):
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.validate_certs = validate_certs
        self.timeout = timeout
        self.url_username = url_username
        self.url_password = url_password
        self.force_basic_auth = force_basic_auth
        self.cookies = CookieJar()

    def url_for(self, path, params=None):
        url = path if path.startswith("http") else self.base_url + path
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        return url

    def request(self, method, path, params=None, json_body=None, headers=None, allow_status=()):
        """Perform a request and return ``(status, parsed_json_or_None)``.

        Raises ``ApiError`` on network errors and HTTP errors not in ``allow_status``.
        """
        url = self.url_for(path, params)
        req_headers = dict(self.headers)
        req_headers.update(headers or {})
        data = None
        if json_body is not None:
            data = json.dumps(json_body)
            req_headers.setdefault("Content-Type", "application/json")
        try:
            response = open_url(
                url,
                method=method,
                data=data,
                headers=req_headers,
                validate_certs=self.validate_certs,
                timeout=self.timeout,
                url_username=self.url_username,
                url_password=self.url_password,
                force_basic_auth=self.force_basic_auth,
                cookies=self.cookies,
            )
            status = response.getcode()
            body = response.read()
        except HTTPError as exc:
            if exc.code in allow_status:
                return exc.code, None
            detail = ""
            try:
                detail = to_text(exc.read())[:300]
            except Exception:
                pass
            message = ("HTTP %s from %s %s %s" % (exc.code, method, url, detail)).rstrip()
            raise ApiError(message, status=exc.code, url=url)
        except URLError as exc:
            raise ApiError("Connection to %s failed: %s" % (url, exc.reason), url=url)
        except Exception as exc:  # socket timeouts, SSL errors, ...
            raise ApiError("Request to %s failed: %s" % (url, exc), url=url)

        if not body:
            return status, None
        try:
            return status, json.loads(to_text(body))
        except ValueError:
            raise ApiError("Non-JSON response from %s" % url, status=status, url=url)

    def get(self, path, params=None, **kwargs):
        return self.request("GET", path, params=params, **kwargs)[1]

    def post(self, path, json_body=None, params=None, **kwargs):
        return self.request("POST", path, params=params, json_body=json_body, **kwargs)[1]
