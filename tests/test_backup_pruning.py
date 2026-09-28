# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Backup pruning keeps N database dumps and N archives of each kind
(public files, private files), newest first."""

import os

from sitiame_core import tasks


def make(directory, names):
	for age, name in enumerate(names):
		path = directory / name
		path.write_text("x")
		os.utime(path, (1_000_000 - age, 1_000_000 - age))  # first = newest


def test_keeps_the_newest_of_each_kind(tmp_path, monkeypatch):
	monkeypatch.setattr(tasks, "get_backups_path", lambda: str(tmp_path))
	monkeypatch.setattr(tasks, "BACKUP_KEEP_COUNT", 2)
	monkeypatch.setattr(tasks, "FILES_BACKUP_KEEP_COUNT", 1)
	make(
		tmp_path,
		[
			"3-site-database.sql.gz",
			"3-site-files.tgz",
			"3-site-private-files.tgz",
			"3-site-site_config_backup.json",
			"2-site-database.sql.gz",
			"2-site-files.tgz",
			"2-site-private-files.tgz",
			"1-site-database.sql.gz",
		],
	)

	tasks._prune_old_backups()

	assert sorted(os.listdir(tmp_path)) == [
		"2-site-database.sql.gz",
		"3-site-database.sql.gz",
		"3-site-files.tgz",
		"3-site-private-files.tgz",
		"3-site-site_config_backup.json",
	]


def test_missing_directory_is_ignored(tmp_path, monkeypatch):
	monkeypatch.setattr(tasks, "get_backups_path", lambda: str(tmp_path / "absent"))
	tasks._prune_old_backups()
