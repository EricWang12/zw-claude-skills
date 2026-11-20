"""Tests of claude-groups: grouping, colors, keys and how it spots the left
arrow's relaunch.

run: python3 -m unittest plugins/color-groups/test_claude_groups.py
"""

import json
import re
import subprocess
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

HERE = Path(__file__).parent
loader = SourceFileLoader('claude_groups', str(HERE / 'claude-groups'))
cg = module_from_spec(spec_from_loader('claude_groups', loader))
loader.exec_module(cg)


def session(sid, state, color='', pinned=False, updated='2026-11-07T10:00:00Z', detail=''):
    return {'id': sid, 'name': sid, 'state': state, 'color': color, 'pinned': pinned,
            'detail': detail, 'updated': updated}


SESSIONS = [
    session('top', 'done', 'cyan', pinned=True),
    session('needs', 'blocked', 'blue'),
    session('runs', 'working'),
    session('mesh', 'done', 'blue'),
    session('paper', 'done', 'red'),
    session('old', 'stopped'),
    session('crashed', 'failed', 'blue'),
]


def lines(rows):
    out = []
    for r in rows:
        if r['kind'] == 'section':
            out.append(('section', f'{r["title"]} {r["count"]}'))
        elif r['kind'] == 'group':
            out.append(('group', f'{r["label"]} {r["count"]}'))
        else:
            out.append(('session', r['session']['id']))
    return out


class Grouping(unittest.TestCase):
    def test_completed_is_split_by_color_in_color_order_with_names(self):
        rows = lines(cg.build_rows(SESSIONS, {'blue': {'name': 'generation'}}, 'completed'))
        self.assertEqual(rows, [
            ('section', 'Pinned 1'), ('session', 'top'),
            ('section', 'Needs input 1'), ('session', 'needs'),
            ('section', 'Working 1'), ('session', 'runs'),
            ('section', 'Completed 4'),
            ('group', 'red 1'), ('session', 'paper'),
            ('group', 'generation 2'), ('session', 'mesh'), ('session', 'crashed'),
            ('group', 'no color 1'), ('session', 'old'),
        ])

    def test_all_groups_every_session_by_color_alone(self):
        rows = lines(cg.build_rows(SESSIONS, {}, 'all'))
        self.assertEqual(rows[:5], [
            ('group', 'red 1'), ('session', 'paper'),
            ('group', 'blue 3'), ('session', 'needs'), ('session', 'mesh'),
        ])
        self.assertNotIn('section', [kind for kind, _ in rows])

    def test_a_folded_heading_keeps_its_line_and_hides_its_sessions(self):
        rows = lines(cg.build_rows(SESSIONS, {}, 'completed', {'color:blue', 'section:Working'}))
        self.assertIn(('section', 'Working 1'), rows)
        self.assertNotIn(('session', 'runs'), rows)
        self.assertIn(('group', 'blue 2'), rows)
        self.assertNotIn(('session', 'mesh'), rows)
        self.assertIn(('session', 'paper'), rows)
        folded = cg.build_rows(SESSIONS, {}, 'completed', {'section:Completed'})
        self.assertNotIn('group', [r['kind'] for r in folded])

    def test_off_keeps_the_agent_views_sections_only(self):
        rows = lines(cg.build_rows(SESSIONS, {}, 'off'))
        self.assertNotIn('group', [kind for kind, _ in rows])
        self.assertEqual([item for kind, item in rows if kind == 'section'],
                         ['Pinned 1', 'Needs input 1', 'Working 1', 'Completed 4'])

    def test_a_group_carries_its_note_and_a_note_alone_keeps_the_color_name(self):
        labels = {'blue': {'name': 'generation', 'note': 'meshes and textures'},
                  'red': {'note': 'urgent'}}
        groups = {r['color']: r for r in cg.build_rows(SESSIONS, labels, 'completed') if r['kind'] == 'group'}
        self.assertEqual((groups['blue']['label'], groups['blue']['note']), ('generation', 'meshes and textures'))
        self.assertEqual((groups['red']['label'], groups['red']['note']), ('red', 'urgent'))
        self.assertEqual(groups['']['note'], '')


class Labels(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            saved, cg.NAMES = cg.NAMES, Path(tmp) / 'claude-groups.json'
            try:
                if text is not None:
                    cg.NAMES.write_text(text)
                return cg.read_labels()
            finally:
                cg.NAMES = saved

    def test_names_and_notes_are_read_and_a_first_version_file_still_works(self):
        self.assertEqual(self.read('{"blue": {"name": "generation", "note": "meshes"}}'),
                         {'blue': {'name': 'generation', 'note': 'meshes'}})
        self.assertEqual(self.read('{"blue": "generation", "red": {"note": "urgent"}}'),
                         {'blue': {'name': 'generation'}, 'red': {'note': 'urgent'}})

    def test_a_missing_or_broken_file_is_no_labels(self):
        self.assertEqual(self.read(None), {})
        self.assertEqual(self.read('{broken'), {})
        self.assertEqual(self.read('["blue"]'), {})

    def test_labels_written_are_read_back_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved, cg.NAMES = cg.NAMES, Path(tmp) / 'sub' / 'claude-groups.json'
            try:
                labels = {'blue': {'name': '生成', 'note': 'meshes · textures'}}
                cg.write_labels(labels)
                self.assertEqual(cg.read_labels(), labels)
            finally:
                cg.NAMES = saved


class Colors(unittest.TestCase):
    def test_256_codes_match_what_claude_code_draws(self):
        # Codes seen in a capture of `claude agents` (2.1.319, dark theme) in tmux.
        seen = {'blue': 110, 'purple': 140, 'cyan': 37, 'green': 35, 'pink': 175, 'red': 167}
        for color, code in seen.items():
            self.assertEqual(cg.ansi256(*cg.AGENT[color]), code, color)
        self.assertEqual(cg.ansi256(*cg.GRAY), 246)
        self.assertEqual(cg.ansi256(*cg.WARNING), 220)
        self.assertEqual(cg.ansi256(*cg.INK), 16)
        self.assertEqual(cg.ansi256(*cg.FOCUS), 237)

    def test_a_colored_name_is_a_chip_of_black_on_its_color(self):
        cg.TRUECOLOR = True
        text = cg.session_row(session('mesh', 'done', 'blue'), 100, False, 'completed', 0)
        self.assertIn('\x1b[48;2;106;155;204m\x1b[38;2;0;0;0mmesh', text)
        plain = cg.session_row(session('old', 'stopped'), 100, False, 'completed', 0)
        self.assertNotIn('\x1b[48;2', plain)

    def test_a_row_takes_exactly_the_width(self):
        cg.TRUECOLOR = True
        long = session('仿真' * 40, 'blocked', 'pink', detail='细节 ' * 60)
        for width in (40, 80, 150):
            text = cg.session_row(long, width, True, 'completed', 0)
            self.assertEqual(cg.cells(re.sub(r'\x1b\[[0-9;]*m', '', text)), width)


class Width(unittest.TestCase):
    def test_wide_characters_take_two_cells(self):
        self.assertEqual(cg.cells('ab'), 2)
        self.assertEqual(cg.cells('仿真'), 4)
        self.assertEqual(cg.fit('仿真ab', 3), '仿')
        self.assertEqual(cg.cut('仿真ab', 3), '仿…')
        self.assertEqual(cg.cut('ab', 3), 'ab')


class Keys(unittest.TestCase):
    def test_arrows_controls_and_text(self):
        self.assertEqual(cg.parse('\x1b[A\x1bOB\x1b[D\rq\x18\x13\x07\x0f\x03'),
                         ['up', 'down', 'left', 'enter', 'q', 'ctrl+x', 'ctrl+s', 'ctrl+g', 'ctrl+o', 'ctrl+c'])
        self.assertEqual(cg.parse('\x1b'), ['esc'])
        self.assertEqual(cg.parse('\x1b[5~\x1b[6~'), ['pgup', 'pgdn'])

    def test_a_paste_is_text_with_its_line_breaks_as_spaces(self):
        self.assertEqual(cg.parse('\x1b[200~fix it\nnow\x1b[201~\r'),
                         list('fix it now') + ['enter'])

    def test_mouse_reports_are_presses_releases_moves_and_wheel(self):
        self.assertEqual(cg.parse('\x1b[<0;12;7M\x1b[<0;12;7m\x1b[<35;40;9M\x1b[<65;3;3M'), [
            ('mouse', 0, 12, 7, True), ('mouse', 0, 12, 7, False),
            ('mouse', 35, 40, 9, True), ('mouse', 65, 3, 3, True)])


class Focus(unittest.TestCase):
    def test_a_hidden_focus_moves_to_the_nearest_shown_session(self):
        old = ['a', 'b', 'c', 'd', 'e']
        self.assertEqual(cg.nearest('c', old, ['a', 'b', 'd', 'e']), 'd')
        self.assertEqual(cg.nearest('e', old, ['a', 'b']), 'b')
        self.assertEqual(cg.nearest('c', old, ['a', 'b', 'c']), 'c')
        self.assertEqual(cg.nearest('z', old, ['b', 'c']), 'b')
        self.assertIsNone(cg.nearest('c', old, []))


class Clicks(unittest.TestCase):
    def test_each_drawn_line_says_what_a_click_there_hits(self):
        cg.TRUECOLOR = True
        rows = cg.build_rows(SESSIONS, {}, 'completed')
        _, _, hits = cg.render(120, 40, rows, SESSIONS, 'mesh', 0, 'completed', '', '', '', 0)
        # three header lines, then the rows in order, one line each
        self.assertEqual(hits[4], ('heading', 'section:Pinned'))
        self.assertEqual(hits[5], ('session', 'top'))
        drawn = [hits[line] for line in sorted(hits)]
        self.assertIn(('heading', 'color:blue'), drawn)
        self.assertEqual(drawn.index(('session', 'mesh')), drawn.index(('heading', 'color:blue')) + 1)


class Notes(unittest.TestCase):
    def heading(self, width, labels):
        cg.TRUECOLOR = True
        rows = cg.build_rows(SESSIONS, labels, 'completed')
        screen, _, hits = cg.render(width, 40, rows, SESSIONS, 'mesh', 0, 'completed', '', '', '', 0)
        line = next(line for line, hit in hits.items() if hit == ('heading', 'color:blue'))
        drawn = screen.split(f'\x1b[{line};1H')[1].split('\x1b[K')[0]
        return re.sub(r'\x1b\[[0-9;]*m', '', drawn)

    def test_the_note_follows_the_heading_and_its_count(self):
        text = self.heading(120, {'blue': {'name': 'generation', 'note': 'meshes and textures'}})
        self.assertEqual(text, '  generation   2  meshes and textures')

    def test_a_long_note_is_cut_to_the_width(self):
        text = self.heading(40, {'blue': {'name': 'generation', 'note': 'meshes ' * 20}})
        self.assertLessEqual(cg.cells(text), 40)
        self.assertTrue(text.endswith('…'))

    def test_the_prompt_shows_the_question(self):
        cg.TRUECOLOR = True
        screen, _, _ = cg.render(120, 40, [], SESSIONS, None, 0, 'completed', 'meshes',
                                 'note for generation (empty: none): ', '', 0)
        self.assertIn('note for generation (empty: none): ', re.sub(r'\x1b\[[0-9;]*m', '', screen))


class Loading(unittest.TestCase):
    def test_reads_state_files_newest_first_and_skips_broken_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Path(tmp)
            for sid, body in {
                'a': {'name': 'first', 'state': 'done', 'color': 'blue', 'updatedAt': '2026-11-07T09:00:00Z'},
                'b': {'name': 'second', 'state': 'blocked', 'needs': 'pick one', 'pinned': True,
                      'updatedAt': '2026-11-07T11:00:00Z'},
                'c': {'name': 'no state'},
            }.items():
                (jobs / sid).mkdir()
                (jobs / sid / 'state.json').write_text(json.dumps(body))
            (jobs / 'd').mkdir()
            (jobs / 'd' / 'state.json').write_text('{broken')
            (jobs / 'e').mkdir()

            found = cg.load_sessions(jobs)

        self.assertEqual([s['id'] for s in found], ['b', 'a'])
        self.assertEqual(found[0]['detail'], 'pick one')
        self.assertTrue(found[0]['pinned'])
        self.assertEqual(found[1]['color'], 'blue')


class Relaunch(unittest.TestCase):
    def test_spots_a_process_that_turned_into_the_agent_view(self):
        # A shell that replaces itself with a program whose argv[1] is "agents",
        # as `claude attach` does on the left arrow: `cat agents` on a FIFO,
        # which waits there for a writer.
        with tempfile.TemporaryDirectory() as tmp:
            child = subprocess.Popen(['bash', '-c', 'mkfifo agents; sleep 0.3; exec cat agents'], cwd=tmp)
            try:
                time.sleep(0.1)
                self.assertFalse(cg.is_agent_view(child.pid))
                time.sleep(0.6)
                self.assertTrue(cg.is_agent_view(child.pid))
            finally:
                child.kill()
                child.wait()

    def test_a_missing_process_is_not_the_agent_view(self):
        self.assertFalse(cg.is_agent_view(2 ** 22 + 1))


if __name__ == '__main__':
    unittest.main()
