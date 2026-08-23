# TaskKeeper

## Setup

```bash
pip install -r requirements.txt
```

## First run (no existing data)

```bash
streamlit run app_streamlit.py
```

Creates `data/taskkeeper.db` and self-seeds it with a small sample chore/
grocery/one-time-task set so the app isn't empty on first launch.

## Migrating your real data from the original app

If you have the original app's `data/` folder (`tasklist.json`,
`onetime_tasks.json`, `groceries.json`):

```bash
python migrate_legacy_data.py --data-dir /path/to/old/data --db-path data/taskkeeper.db
```

This is a one-time, one-directional import. It refuses to run if
`data/taskkeeper.db` already has data in it — pass `--force` if you
really want to overwrite (e.g. re-running after fixing something in the
old JSON files):

```bash
python migrate_legacy_data.py --data-dir /path/to/old/data --db-path data/taskkeeper.db --force
```

`legacy_data/` in this repo is a copy of a real original-app data folder,
useful for trying the migration script risk-free before pointing it at
your actual data:

```bash
python migrate_legacy_data.py --data-dir legacy_data --db-path /tmp/try_it.db
```

### Category inference

The old schema had no `category` field — the original app used an emoji
prefix in each task's name as an informal category marker. The migration
script makes that explicit by mapping known emoji (🍴 kitchen, 😺 pet, 🌱
garden, 🚘 car, 👕 laundry, 🛏/🛌 bedroom, 🛋️ living room, 📞 admin, ⚔
hobby) to a real `Category`. Anything it doesn't recognize falls back to
`Other` and is listed in the migration report — check the Library tab
afterward and recategorize anything that landed there.

## Where your data lives

Everything is in the single SQLite file at `data/taskkeeper.db` (or
wherever `TASKKEEPER_DB_PATH` points, if you set that environment
variable). Back it up like any other file — the in-app "Backup library" /
"Backup list" buttons export a JSON snapshot for a lighter-weight,
human-readable backup of just the chores or groceries table.

## Running the test scripts

There's no committed pytest suite yet — verification so far has been a
set of one-off scripts run against the code (service-layer round-trips,
ChangeLog baseline semantics, the migration's data-integrity checks, and
`streamlit.testing.v1.AppTest` for full-app smoke tests). Worth turning
into a real `tests/` directory with pytest before this goes much further.
