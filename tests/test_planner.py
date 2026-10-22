"""Planner rules, week accounting and preservation of user-owned daily lists."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import daily
import planner
import server


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.notes = Path(self.tmp.name)
        (self.notes / 'claude').mkdir()
        (self.notes / 'daily').mkdir()
        self.config = dict(enabled=True, study_days=4, study_minutes=120,
                           assignment_minutes=60, gym_days=4, gym_minutes=45,
                           laundry_weekday=2, courses={'STAT252': {'quiz_material_weekday': 2}})
        self.save_config()
        (self.notes / 'now.md').write_text('## Upcoming\n- 2026-10-23 13:30 · STAT252 Quiz\n- 2026-10-22 · CISC 235 Test\n- 2026-10-22 · CISC223 Assignment Due\n\nCalendar synced 2026-10-21.\n', encoding='utf-8')

    def save_config(self):
        (self.notes / planner.CONFIG).write_text('```json\n' + json.dumps(self.config) + '\n```\n', encoding='utf-8')

    def titles(self, date):
        return [t['text'] for t in planner.generate(self.notes, date)[0]]

    def test_wednesday_checklist_and_no_specific_times(self):
        titles = self.titles('2026-10-21')
        self.assertIn('Study for STAT252', titles)
        self.assertIn('Study for CISC235', titles)
        self.assertIn('Do CISC223 Assignment', titles)
        self.assertIn('Do laundry', titles)
        self.assertFalse(any('09:00' in title for title in titles))

    def test_material_release_and_four_preceding_days(self):
        self.assertNotIn('Study for STAT252', self.titles('2026-10-20'))
        self.assertIn('Study for STAT252', self.titles('2026-10-22'))
        self.assertNotIn('Study for STAT252', self.titles('2026-10-23'))
        work = lambda date: planner.schoolwork(dt.date.fromisoformat(date), [(dt.date(2026, 10, 27), 'STAT252 Midterm')], self.config)
        self.assertEqual(work('2026-10-22'), [])
        self.assertEqual(work('2026-10-23'), [('Study for STAT252', 120)])
        self.assertEqual(work('2026-10-26'), [('Study for STAT252', 120)])

    def test_course_overrides_and_overlapping_tests_share_study(self):
        self.config['courses']['CISC235'] = {'study_days': 2, 'study_minutes': 60}
        work = planner.schoolwork(dt.date(2026, 10, 21), [(dt.date(2026, 10, 22), 'CISC235 Test'), (dt.date(2026, 10, 23), 'CISC235 Quiz')], self.config)
        self.assertEqual(work, [('Study for CISC235', 60)])

    def test_four_gym_days_and_completed_history(self):
        # Simulate following each generated day across the week.
        count = 0
        for offset in range(7):
            date = (dt.date(2026, 10, 19) + dt.timedelta(days=offset)).isoformat()
            tasks, _ = planner.generate(self.notes, date)
            for task in tasks:
                task['done'] = True
                count += task['text'] == 'Go to the gym'
            (self.notes / 'daily' / (date + '.md')).write_text(daily.render(date, tasks), encoding='utf-8')
        self.assertEqual(count, 4)

    def test_completed_assignment_does_not_repeat_on_due_day(self):
        tasks, _ = planner.generate(self.notes, '2026-10-21')
        for task in tasks:
            task['done'] = True
        (self.notes / 'daily/2026-10-21.md').write_text(daily.render('2026-10-21', tasks), encoding='utf-8')
        self.assertNotIn('Do CISC223 Assignment', self.titles('2026-10-22'))

    def test_server_generates_once_and_preserves_edits_and_plan_note(self):
        with patch.object(server, 'NOTES', str(self.notes)), patch.object(server, 'today', return_value='2026-10-21'):
            first = server.daily_state()
            key = first['tasks'][0]['id']
            server.act_daily(dict(date='2026-10-21', action='set', id=key, done=True))
            self.assertTrue(server.daily_state()['tasks'][0]['done'])
            self.assertIn('plan_note', server.daily_state())
            server.act_daily(dict(date='2026-10-21', action='remove', id=key))
            self.assertNotIn(key, [t['id'] for t in server.daily_state()['tasks']])
        server.TOUCHED.clear()

    def test_stale_calendar_is_visible_and_config_is_opt_in(self):
        self.assertIn('not refreshed today', planner.generate(self.notes, '2026-10-22')[1])
        (self.notes / planner.CONFIG).unlink()
        self.assertEqual(planner.generate(self.notes, '2026-10-21'), ([], ''))

    def test_invalid_config(self):
        self.config['study_minutes'] = -1
        self.save_config()
        with self.assertRaises(ValueError):
            planner.generate(self.notes, '2026-10-21')
