"""
Popup JS Tests
===============

Behavior tests for popup.js DOM update logic, executed with Node.js
against a minimal DOM stub.  Skipped when Node.js is not installed -
the app itself never needs Node; it is only used as a test runner
for the popup's JavaScript.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_POPUP_JS = Path(__file__).parent.parent / 'usage_monitor_for_claude' / 'popup' / 'popup.js'

_NODE = shutil.which('node')

# Minimal DOM stub covering exactly the APIs the bar create/update path uses.
_DOM_STUB = r'''
class StubElement {
    constructor(tag) {
        this.tagName = tag;
        this.className = '';
        this.textContent = '';
        this.title = '';
        this.style = {};
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        const element = this;
        this.classList = {
            toggle(name, force) {
                const classes = element._classSet();
                const on = force === undefined ? !classes.has(name) : !!force;
                if (on) classes.add(name); else classes.delete(name);
                element.className = [...classes].join(' ');
                return on;
            },
            add(name) { const classes = element._classSet(); classes.add(name); element.className = [...classes].join(' '); },
            remove(name) { const classes = element._classSet(); classes.delete(name); element.className = [...classes].join(' '); },
            contains(name) { return element._classSet().has(name); },
        };
    }
    _classSet() { return new Set(this.className.split(/\s+/).filter(Boolean)); }
    appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
    append(...nodes) { for (const node of nodes) this.appendChild(node); }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index >= 0) this.parentNode.children.splice(index, 1);
            this.parentNode = null;
        }
    }
    matches(selector) { return selector.startsWith('.') && this._classSet().has(selector.slice(1)); }
    querySelector(selector) {
        for (const child of this.children) {
            if (child.matches(selector)) return child;
            const nested = child.querySelector(selector);
            if (nested) return nested;
        }
        return null;
    }
    querySelectorAll(selector) {
        const found = [];
        for (const child of this.children) {
            if (child.matches(selector)) found.push(child);
            found.push(...child.querySelectorAll(selector));
        }
        return found;
    }
}

globalThis.document = {
    createElement: (tag) => new StubElement(tag),
    body: new StubElement('body'),
};
globalThis.ResizeObserver = class { constructor() {} observe() {} };
globalThis.requestAnimationFrame = (callback) => callback();
'''

_SCENARIO_PRELUDE = r'''
els = { usageBars: document.createElement('div') };

function makeEntry(overrides) {
    return Object.assign({
        key: 'five_hour', label: '5h', pct_text: '0%', fill_pct: 0.0,
        warn: false, dividers: [], marker_rel: null, reset_text: '',
    }, overrides);
}

// Full element set for the scenarios that drive updateData() end to end.
function makeEls() {
    const names = [
        'accountSection', 'emailRow', 'emailValue', 'planRow', 'planValue',
        'usageSection', 'headingUsage', 'usageBars',
        'extraSection', 'extraSpent', 'extraPct', 'extraBarContainer', 'extraFill', 'extraBalance',
        'installSection', 'installRows', 'statusSection', 'statusText', 'planBadge', 'appContainer',
    ];
    return Object.fromEntries(names.map((name) => [name, document.createElement('div')]));
}

function makeExtra(overrides) {
    return Object.assign({
        has_limit: true, pct_text: '25%', fill_pct: 0.25, spent_text: '$25.00 / $100.00 spent', balance_text: '',
    }, overrides);
}
'''


def _run_scenario(scenario: str) -> dict:
    """Execute the DOM stub + popup.js + scenario with Node and parse its JSON output."""
    script = _DOM_STUB + _POPUP_JS.read_text(encoding='utf-8') + _SCENARIO_PRELUDE + scenario
    with TemporaryDirectory() as tmp:
        script_path = Path(tmp) / 'scenario.js'
        script_path.write_text(script, encoding='utf-8')
        proc = subprocess.run([_NODE, str(script_path)], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(f'Node scenario failed:\n{proc.stderr}')
    return json.loads(proc.stdout)


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestUsageBarUpdates(unittest.TestCase):
    """Tests for updateUsageBars/updateBarElement in popup.js."""

    def test_changed_field_set_with_equal_count_updates_labels(self):
        """When the set of quota fields changes but the count stays the same
        (e.g. an account switch between plans), the bars must not show the new
        percentages under the old labels."""
        result = _run_scenario('''
updateUsageBars([
    makeEntry({ key: 'five_hour', label: '5h', pct_text: '10%' }),
    makeEntry({ key: 'seven_day', label: '7d', pct_text: '20%' }),
]);
updateUsageBars([
    makeEntry({ key: 'five_hour', label: '5h', pct_text: '30%' }),
    makeEntry({ key: 'seven_day_opus', label: '7d Opus', pct_text: '99%' }),
]);
console.log(JSON.stringify(els.usageBars.children.map((bar) => ({
    label: bar.children[0].children[0].textContent,
    pct: bar.querySelector('.bar-pct').textContent,
}))));
''')
        self.assertEqual(result, [
            {'label': '5h', 'pct': '30%'},
            {'label': '7d Opus', 'pct': '99%'},
        ])

    def test_marker_and_divider_positions_stable_across_update(self):
        """The 2 px marker/divider elements are centered with a -1px correction
        on create; an in-place update must use the identical expression, or the
        elements shift by 1 px after the first data update."""
        result = _run_scenario('''
const fields = { key: 'five_hour', label: '5h', marker_rel: 0.5, dividers: [0.25] };
updateUsageBars([makeEntry(Object.assign({ pct_text: '10%' }, fields))]);
const container = els.usageBars.children[0].querySelector('.bar-container');
const before = {
    marker: container.querySelector('.bar-marker').style.left,
    divider: container.querySelector('.bar-divider').style.left,
};
updateUsageBars([makeEntry(Object.assign({ pct_text: '11%' }, fields))]);
const after = {
    marker: container.querySelector('.bar-marker').style.left,
    divider: container.querySelector('.bar-divider').style.left,
};
console.log(JSON.stringify({ before, after }));
''')
        self.assertEqual(result['after'], result['before'])

    def test_unchanged_field_set_updates_in_place(self):
        """With an unchanged field set, bars are updated in place (no rebuild)."""
        result = _run_scenario('''
updateUsageBars([makeEntry({ key: 'five_hour', label: '5h', pct_text: '10%' })]);
const barBefore = els.usageBars.children[0];
updateUsageBars([makeEntry({ key: 'five_hour', label: '5h', pct_text: '50%', fill_pct: 0.5 })]);
console.log(JSON.stringify({
    sameElement: els.usageBars.children[0] === barBefore,
    pct: els.usageBars.children[0].querySelector('.bar-pct').textContent,
    fillWidth: els.usageBars.children[0].querySelector('.bar-fill').style.width,
}));
''')
        self.assertEqual(result, {'sameElement': True, 'pct': '50%', 'fillWidth': '50%'})


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestExtraUsageSection(unittest.TestCase):
    """Tests for the prepaid balance line in the extra-usage section."""

    def test_balance_line_shown_when_present(self):
        """A rendered balance is shown below the extra-usage bar."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: makeExtra({ balance_text: '$55.97 available' }), installations: [], status: null });
console.log(JSON.stringify({ text: els.extraBalance.textContent, display: els.extraBalance.style.display }));
''')
        self.assertEqual(result, {'text': '$55.97 available', 'display': ''})

    def test_balance_line_hidden_when_absent(self):
        """Without a balance the line is hidden, leaving the section as it was before."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: makeExtra(), installations: [], status: null });
const empty = { text: els.extraBalance.textContent, display: els.extraBalance.style.display };
updateData({ profile: null, usage: [], extra: makeExtra({ balance_text: undefined }), installations: [], status: null });
const missing = { text: els.extraBalance.textContent, display: els.extraBalance.style.display };
console.log(JSON.stringify({ empty, missing }));
''')
        self.assertEqual(result, {
            'empty': {'text': '', 'display': 'none'},
            'missing': {'text': '', 'display': 'none'},
        })

    def test_balance_line_cleared_on_update(self):
        """A balance that becomes unavailable is removed instead of lingering."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: makeExtra({ balance_text: '$55.97 available' }), installations: [], status: null });
updateData({ profile: null, usage: [], extra: makeExtra(), installations: [], status: null });
console.log(JSON.stringify({ text: els.extraBalance.textContent, display: els.extraBalance.style.display }));
''')
        self.assertEqual(result, {'text': '', 'display': 'none'})


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestPlanBadge(unittest.TestCase):
    """Tests for updatePlanBadge() - the subscription-tier badge and Max glow."""

    def test_max_shows_badge_and_glow_class(self):
        """A Max plan shows the badge and flags the glow border on the container."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'max' });
console.log(JSON.stringify({
    text: els.planBadge.textContent,
    visible: els.planBadge.classList.contains('visible'),
    badgeMax: els.planBadge.classList.contains('plan-max'),
    containerMax: els.appContainer.classList.contains('plan-max'),
}));
''')
        self.assertEqual(result, {'text': 'Max', 'visible': True, 'badgeMax': True, 'containerMax': True})

    def test_pro_shows_badge_without_glow(self):
        """A Pro plan shows the badge but never the Max glow border."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'pro' });
console.log(JSON.stringify({
    text: els.planBadge.textContent,
    visible: els.planBadge.classList.contains('visible'),
    containerMax: els.appContainer.classList.contains('plan-max'),
}));
''')
        self.assertEqual(result, {'text': 'Pro', 'visible': True, 'containerMax': False})

    def test_no_plan_hides_badge(self):
        """A missing or unrecognized plan shows no badge and no glow."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: null });
console.log(JSON.stringify({
    visible: els.planBadge.classList.contains('visible'),
    containerMax: els.appContainer.classList.contains('plan-max'),
}));
''')
        self.assertEqual(result, {'visible': False, 'containerMax': False})

    def test_toggle_calm_stops_glow_and_toggles_back(self):
        """Clicking the Max badge switches to calm mode and a second click restores the glow."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'max' });
toggleMaxCalm();
const calm = { badge: els.planBadge.classList.contains('calm'), container: els.appContainer.classList.contains('calm') };
toggleMaxCalm();
const restored = { badge: els.planBadge.classList.contains('calm'), container: els.appContainer.classList.contains('calm') };
console.log(JSON.stringify({ calm, restored }));
''')
        self.assertEqual(result, {
            'calm': {'badge': True, 'container': True},
            'restored': {'badge': False, 'container': False},
        })

    def test_calm_survives_data_refresh(self):
        """The periodic data push must not reset a calm choice."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'max' });
toggleMaxCalm();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'max' });
console.log(JSON.stringify({ container: els.appContainer.classList.contains('calm') }));
''')
        self.assertEqual(result, {'container': True})

    def test_calm_never_applies_to_pro(self):
        """Calm is a Max-only state: Pro must not carry it."""
        result = _run_scenario('''
els = makeEls();
toggleMaxCalm();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'pro' });
console.log(JSON.stringify({ container: els.appContainer.classList.contains('calm') }));
''')
        self.assertEqual(result, {'container': False})

    def test_switching_from_max_to_pro_clears_glow(self):
        """Switching accounts from Max to Pro must drop the glow, not just stop adding it."""
        result = _run_scenario('''
els = makeEls();
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'max' });
updateData({ profile: null, usage: [], extra: null, installations: [], status: null, plan: 'pro' });
console.log(JSON.stringify({ containerMax: els.appContainer.classList.contains('plan-max') }));
''')
        self.assertEqual(result, {'containerMax': False})


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestUsageColor(unittest.TestCase):
    """Tests for the single green -> orange -> red colour a bar takes from its usage."""

    def test_color_endpoints_and_midpoint(self):
        """Low usage is green, half is Claude orange, full is red; out-of-range clamps."""
        result = _run_scenario('''
console.log(JSON.stringify([usageColor(0), usageColor(0.5), usageColor(1), usageColor(2), usageColor(-1)]));
''')
        self.assertEqual(result, ['hsl(140.0, 50.0%, 50.0%)', 'hsl(15.0, 63.0%, 60.0%)', 'hsl(-2.0, 74.0%, 59.0%)',
                                  'hsl(-2.0, 74.0%, 59.0%)', 'hsl(140.0, 50.0%, 50.0%)'])

    def test_any_usage_lights_at_least_one_segment(self):
        """1% must not round down to an empty bar; zero stays empty."""
        result = _run_scenario('''
console.log(JSON.stringify([filledSegmentCount(0.01, 25), filledSegmentCount(0, 25), filledSegmentCount(0.5, 25)]));
''')
        self.assertEqual(result, [1, 0, 13])

    def test_every_lit_segment_shares_one_colour(self):
        """The whole filled bar is one colour; unlit segments carry none."""
        result = _run_scenario('''
const div = createBarElement(makeEntry({ fill_pct: 0.04 }));
updateBarElement(div, makeEntry({ fill_pct: 0.4 }));
const segments = div.querySelectorAll('.compact-segment');
const lit = segments.slice(0, 10).map((s) => s.style.background);
console.log(JSON.stringify({ distinct: [...new Set(lit)].length, dark: segments[10].style.background, color: lit[0] }));
''')
        self.assertEqual(result['distinct'], 1)
        self.assertEqual(result['dark'], '')
        self.assertTrue(result['color'].startswith('hsl('))


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestCompactBarSet(unittest.TestCase):
    """The compact popup shows only the session and weekly bars."""

    def test_only_session_and_weekly_render(self):
        """Per-model and future quota bars are dropped."""
        result = _run_scenario('''
els = makeEls();
const bars = [makeEntry({ key: 'five_hour', label: 'Session' }), makeEntry({ key: 'seven_day', label: 'Weekly' }),
              makeEntry({ key: 'seven_day_sonnet', label: 'Weekly (Sonnet)' }), makeEntry({ key: 'seven_day_opus', label: 'Weekly (Opus)' }),
              makeEntry({ key: 'seven_day_fable', label: 'Weekly (Fable)' }), makeEntry({ key: 'monthly_new', label: 'New' })];
updateData({ profile: null, usage: bars, extra: null, installations: [], status: null });
console.log(JSON.stringify(els.usageBars.children.map((child) => child.dataset.key)));
''')
        self.assertEqual(result, ['five_hour', 'seven_day'])
