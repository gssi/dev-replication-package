"""Regenerate the aggregate participant charts embedded in the landing page.

Run from any directory with a Python environment containing pandas and openpyxl.
Multi-select percentages count each option once per respondent and use the
number of nonblank responses to that question as their denominator.
"""
import json
import math
from collections import Counter
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
START = '          <!-- participant-charts:start -->'
END = '          <!-- participant-charts:end -->'


def selections(value, multiple):
    return set(part.strip() for part in (value.split(', ') if multiple else [value]) if part.strip())


PALETTE = ['#3458cc', '#169b97', '#bd6437', '#8b56a2', '#b48a19', '#567387', '#a4aab3']


def geography_chart(title, counts, denominator):
    """Return inline SVG charts so they also work offline and support tooltips."""
    labels = sorted(counts, key=lambda label: (-counts[label], label))
    rows = ''.join(f'<tr><th scope="row">{escape(label)}</th><td>{counts[label]}</td><td>{100 * counts[label] / denominator:.1f}%</td></tr>' for label in labels)
    table = f'<details><summary>View counts and percentages</summary><div class="table-scroll"><table><thead><tr><th scope="col">Location</th><th scope="col">Respondents</th><th scope="col">Percentage</th></tr></thead><tbody>{rows}</tbody></table></div></details>'
    if title.endswith('country'):
        # Natural Earth 1:110m admin-0 boundaries (public domain), rounded to 0.01°.
        # Source: github.com/nvkelso/natural-earth-vector, geojson/ne_110m_admin_0_countries.geojson
        boundaries = json.loads((ROOT / 'rq1/world_countries.json').read_text())
        maximum = max(counts.values())
        shapes = []
        covered = set()
        for feature in boundaries:
            name = {'United States of America': 'United States'}.get(feature['name'], feature['name'])
            count = counts.get(name, 0)
            if count:
                covered.add(name)
            # A linear sequential color scale: pale blue to dark blue.
            fraction = count / maximum
            rgb = tuple(round(a + (b - a) * fraction) for a, b in zip((221, 234, 251), (35, 66, 160)))
            fill = '#%02x%02x%02x' % rgb if count else '#edf0f4'
            geometry = feature['geometry']
            polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
            paths = []
            for polygon in polygons:
                for ring in polygon:
                    points = [((lon + 180) * 2.5, (85 - lat) * 2.5) for lon, lat in ring]
                    paths.append('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in points) + 'Z')
            tooltip = f'{name}: {count} respondents ({100 * count / denominator:.1f}%)' if count else f'{name}: no respondents'
            focus = ' tabindex="0"' if count else ''
            shapes.append(f'<path d="{"".join(paths)}" fill="{fill}" stroke="#fff" stroke-width="0.55" fill-rule="evenodd"{focus} aria-label="{escape(tooltip)}"><title>{escape(tooltip)}</title></path>')
        assert covered == set(counts) - {'Unclassified / not specified'}, set(counts) - covered
        graphic = '<svg class="country-map" viewBox="0 0 900 390" role="img" aria-labelledby="country-map-title country-map-description"><title id="country-map-title">Company locations by country</title><desc id="country-map-description">World map shaded by respondent count, from pale to dark blue. Exact counts and percentages are in the accompanying table.</desc><rect width="900" height="390" rx="8" fill="#f8fbff"/>' + ''.join(shapes) + '</svg>'
        legend = f'<div class="map-legend"><span>Fewer</span><span class="map-gradient" aria-hidden="true"></span><span>More · {maximum} respondents</span><span><i class="map-no-data" aria-hidden="true"></i>No respondents</span></div>'
        note = f'{counts.get("Unclassified / not specified", 0)} unclassified response is included in percentages but cannot be placed on the map. Hover over a country for its count.'
        return f'<figure class="panel card participant-chart geography-map"><figcaption><h3>{title}</h3><p class="chart-note">Company locations, not nationality or residence. Percentages use all {denominator} respondents.</p></figcaption>{graphic}{legend}<p class="chart-note">{note} Map: <a href="https://www.naturalearthdata.com/about/terms-of-use/">Natural Earth</a> (public domain), equirectangular projection.</p>{table}</figure>'

    slices = []
    legend = []
    angle = -math.pi / 2
    for label, color in zip(labels, PALETTE):
        count = counts[label]
        sweep = 2 * math.pi * count / denominator
        end = angle + sweep
        x1, y1 = 180 + 150 * math.cos(angle), 180 + 150 * math.sin(angle)
        x2, y2 = 180 + 150 * math.cos(end), 180 + 150 * math.sin(end)
        tooltip = f'{label}: {count} respondents ({100 * count / denominator:.1f}%)'
        slices.append(f'<path d="M180,180 L{x1:.3f},{y1:.3f} A150,150 0 {int(sweep > math.pi)},1 {x2:.3f},{y2:.3f} Z" fill="{color}" stroke="white" stroke-width="2" tabindex="0" aria-label="{escape(tooltip)}"><title>{escape(tooltip)}</title></path>')
        if count / denominator >= .045:
            mid = angle + sweep / 2
            x, y = 180 + 108 * math.cos(mid), 180 + 108 * math.sin(mid)
            slices.append(f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="15" font-weight="700" aria-hidden="true">{100 * count / denominator:.1f}%</text>')
        legend.append(f'<li><i style="background:{color}" aria-hidden="true"></i><span>{escape(label)}</span><strong>{count} · {100 * count / denominator:.1f}%</strong></li>')
        angle = end
    assert math.isclose(angle, 3 * math.pi / 2)
    graphic = f'<svg class="continent-pie" viewBox="0 0 360 360" role="img" aria-labelledby="continent-pie-title continent-pie-description"><title id="continent-pie-title">Company locations by continent</title><desc id="continent-pie-description">Pie chart of all {denominator} respondents, including unclassified locations. Exact values appear in the legend.</desc>' + ''.join(slices) + '</svg>'
    return f'<figure class="panel card participant-chart"><figcaption><h3>{title}</h3><p class="chart-note">Company locations, not nationality or residence. Percentages use all {denominator} respondents, including unclassified locations.</p></figcaption>{graphic}<ul class="pie-legend">{"".join(legend)}</ul></figure>'


def build_charts(frame):
    # Exact mappings preserve the original location strings for review. New or
    # non-geographical entries remain unclassified rather than being guessed.
    mapping = json.loads((ROOT / 'rq1/location_mapping.json').read_text())
    frame = frame.copy()
    locations = frame.iloc[:, 4].fillna('').astype(str).str.strip()
    for field in ('country', 'continent'):
        frame[field] = locations.map(lambda value: mapping.get(value, {}).get(field) or 'Unclassified / not specified')
    specifications = [
        (len(frame.columns) - 2, 'Company location by country', False, None),
        (len(frame.columns) - 1, 'Company location by continent', False, None),
        (2, 'Current professional role', False, None),
        (3, 'Professional development experience', False, ['Less than 1 year', '1–2 years', '3–5 years', '6–10 years', 'More than 10 years']),
        (5, 'Primary development context', False, None),
        (6, 'Software application domains', True, None),
        (7, 'Areas of software development', True, None),
        (8, 'Primary users of the software', True, None),
        (9, 'Typical development team size', False, ['I mostly work independently', '2–5 developers', '6–10 developers', '11–50 developers', 'More than 50 developers', 'It varies substantially across projects']),
    ]
    charts = []
    for column, title, multiple, order in specifications:
        responses = [str(value).strip() for value in frame.iloc[:, column].dropna() if str(value).strip()]
        counts = Counter(option for response in responses for option in selections(response, multiple))
        labels = sorted(counts, key=lambda label: (-counts[label], label))
        if order:
            labels = [label for label in order if label in counts] + [label for label in labels if label not in order]
        denominator = len(responses)
        if title.startswith('Company location'):
            charts.append(geography_chart(title, counts, denominator))
            continue
        note = f'{denominator} respondents answered · {len(frame) - denominator} missing.'
        if title.startswith('Company location'):
            note += ' Based on company location, not nationality or residence. Percentages include unclassified entries.'
        if multiple:
            note += ' Multiple selections; each option is counted separately.'
        bars = []
        for label in labels:
            count = counts[label]
            percent = 100 * count / denominator
            assert 0 < count <= denominator
            bars.append(f'                <div><div class="bar-heading"><span>{escape(label)}</span><span>{count} · {percent:.1f}%</span></div><div class="track" aria-hidden="true"><span class="fill" style="width:{percent:.4f}%"></span></div></div>')
        if not multiple:
            assert sum(counts.values()) == denominator
        charts.append('\n'.join([
            f'            <figure class="panel card participant-chart{" teal" if multiple else ""}">',
            f'              <figcaption><h3>{escape(title)}</h3><p class="chart-note">{note}</p></figcaption>',
            '              <div class="bars">', *bars, '              </div>', '            </figure>'
        ]))
    return '\n'.join(charts)


if __name__ == '__main__':
    frame = pd.read_excel(ROOT / 'rq1/developers-answers.xlsx')
    page = ROOT / 'index.html'
    html = page.read_text()
    before, remaining = html.split(START, 1)
    _, after = remaining.split(END, 1)
    page.write_text(before + START + '\n' + build_charts(frame) + '\n' + END + after)
    print(f'Updated nine charts for {len(frame)} participants.')
