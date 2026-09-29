# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""gemini_assistant.generate: keys set aside per model, for as long as the
quota Google reports (production 2026-09-29: one exhausted model locked
every key for an hour, and invoice reading stopped for every account)."""

import frappe
import pytest
import requests

from sitiame_core import gemini_assistant as g


class Response:
	def __init__(self, status_code, body):
		self.status_code, self._body = status_code, body
		self.content = b"x"

	def json(self):
		return self._body


class Cache:
	def __init__(self):
		self.values, self.ttl = {}, {}

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key], self.ttl[key] = value, expires_in_sec

	def delete_value(self, key):
		self.values.pop(key, None)


def ok(text="{}"):
	return Response(200, {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def quota(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier", delay="51s"):
	return Response(429, {"error": {"message": "You exceeded your current quota", "details": [
		{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]},
		{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
	]}})


@pytest.fixture
def api(monkeypatch):
	state = {"responses": [], "calls": [], "cache": Cache()}

	def post(url, json=None, timeout=None):
		model = url.split("/models/")[1].split(":")[0]
		key = url.split("key=")[1]
		state["calls"].append((model, key))
		response = state["responses"].pop(0)
		if isinstance(response, Exception):
			raise response
		return response

	monkeypatch.setattr(g.requests, "post", post)
	monkeypatch.setattr(g.time, "sleep", lambda s: None)
	monkeypatch.setattr(frappe, "cache", lambda: state["cache"], raising=False)
	monkeypatch.setattr(frappe, "conf", frappe._dict(gemini_api_keys=["k1", "k2"]), raising=False)
	return state


def test_a_key_exhausted_on_one_model_still_reads_with_the_next(api):
	api["responses"] = [quota(), quota(), ok()]
	result = g.generate({}, models=["m1", "m2"])
	assert result["ok"]
	assert api["calls"] == [("m1", "k1"), ("m1", "k2"), ("m2", "k1")]


def test_daily_quota_sets_the_key_aside_for_an_hour_on_that_model_only(api):
	api["responses"] = [quota(), ok()]
	g.generate({}, models=["m1"])
	assert api["cache"].ttl[g._key_lockout_cache_key("k1", "m1")] == g.KEY_LOCKOUT_SECONDS
	assert g._available_keys("m1") == ["k2"]
	assert g._available_keys("m2") == ["k1", "k2"]


def test_per_minute_quota_sets_the_key_aside_for_googles_delay(api):
	api["responses"] = [quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "17.4s"), ok()]
	g.generate({}, models=["m1"])
	assert api["cache"].ttl[g._key_lockout_cache_key("k1", "m1")] == 18


def test_a_timeout_skips_to_the_next_model_not_the_next_key(api):
	api["responses"] = [requests.Timeout("slow"), ok()]
	assert g.generate({}, models=["m1", "m2"])["ok"]
	assert api["calls"] == [("m1", "k1"), ("m2", "k1")]


def test_an_overloaded_model_skips_to_the_next_model(api):
	overloaded = Response(503, {"error": {"message": "This model is currently experiencing high demand."}})
	api["responses"] = [overloaded] * g.MAX_ATTEMPTS + [ok()]
	assert g.generate({}, models=["m1", "m2"])["ok"]
	assert api["calls"][-1] == ("m2", "k1")
	assert ("m1", "k2") not in api["calls"]


def test_default_models_are_unchanged_for_the_assistant(api):
	api["responses"] = [ok()]
	g.generate({})
	assert api["calls"] == [(g.DEFAULT_MODEL, "k1")]
