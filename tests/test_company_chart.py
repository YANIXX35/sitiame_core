# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Every new company gets the SYSCOHADA chart with codes (company_chart.py)."""

import sys
import types

import frappe
import pytest

from sitiame_core import company_chart as chart


def company(**fields):
	doc = frappe._dict(name="NOUVELLE PME", **fields)
	doc.flags = frappe._dict()
	return doc


@pytest.mark.parametrize(
	"fields",
	[
		{"create_chart_of_accounts_based_on": "Standard Template", "chart_of_accounts": "Standard"},  # typed in the desk
		{"chart_of_accounts": "Standard with Numbers"},
		{},  # PME360 (Laravel) sends no based_on
		{"create_chart_of_accounts_based_on": "Existing Company"},  # no company to copy from
	],
)
def test_new_company_gets_the_syscohada_chart(fields):
	doc = company(**fields)
	chart.force_syscohada_chart(doc)
	assert (doc.create_chart_of_accounts_based_on, doc.chart_of_accounts) == ("Standard Template", chart.SYSCOHADA_CHART)


def test_copy_of_an_existing_company_keeps_its_chart():
	doc = company(create_chart_of_accounts_based_on="Existing Company", existing_company="SITIAME")
	chart.force_syscohada_chart(doc)
	assert doc.chart_of_accounts is None and doc.existing_company == "SITIAME"


@pytest.fixture
def applied(monkeypatch):
	calls = []
	api = types.ModuleType("sitiame_core.api")
	api._apply_syscohada_defaults = calls.append
	monkeypatch.setitem(sys.modules, "sitiame_core.api", api)
	return calls


def test_defaults_set_once_the_chart_is_built(applied):
	doc = company(chart_of_accounts=chart.SYSCOHADA_CHART)
	doc.flags.in_insert = True
	chart.set_syscohada_defaults(doc)
	assert applied == ["NOUVELLE PME"]


@pytest.mark.parametrize("in_insert, chart_name", [(False, chart.SYSCOHADA_CHART), (True, None)])
def test_defaults_left_alone_on_later_saves_and_copies(applied, in_insert, chart_name):
	"""A later save never resets accounts the accountant changed."""
	doc = company(chart_of_accounts=chart_name)
	doc.flags.in_insert = in_insert
	chart.set_syscohada_defaults(doc)
	assert applied == []
