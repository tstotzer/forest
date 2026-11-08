"""Reflow edited multiline cells without splitting their TeX groups."""
import shutil
import subprocess

import pytest

from research.paper.layout import apply_layout


def table_source(cell):
    return (r'''\documentclass{article}
\usepackage{booktabs}
\begin{document}
\begin{table}
\centering
\begin{tabular}{lr}
\toprule
Label & Value \\
\midrule
''' + cell + r''' & 1 \\
second & 2 \\
third & 3 \\
fourth & 4 \\
fifth & 5 \\
\bottomrule
\end{tabular}
\caption{Synthetic values.}
\end{table}
\end{document}
''')


@pytest.mark.parametrize('cell', [
    r'\shortstack{one\\two\\three\\four\\five}',
    r'\shortstack{\textbf{one}\\two \{three\}\\four\\five}',
    r'\shortstack{one\{\\two\\three\\four\\five}',
    '\\shortstack{one% ignored } and \\\\\n\\\\two\\\\three\\\\four\\\\five}',
])
@pytest.mark.parametrize('columns', ['single', 'double'])
def test_reflow_counts_only_top_level_rows(tmp_path, cell, columns):
    path = tmp_path / 'paper.tex'
    path.write_text(table_source(cell))
    plan = apply_layout(tmp_path, {'columns': columns, 'max_table_rows': 4})
    source = path.read_text()
    assert plan['blocks'][0]['rows'] == 5
    assert plan['blocks'][0]['panels'] == 2
    assert source.count('\\begin{tabular}') == 2
    assert source.count(cell) == 1
    assert all(source.count(f'{name} & {value}') == 1 for name, value in
               [('second', 2), ('third', 3), ('fourth', 4), ('fifth', 5)])


@pytest.mark.parametrize('cell', [
    r'\begin{minipage}{2cm}one\\two\end{minipage}',
    r'\verb|one{\\two}|',
    r'\shortstack{one\\two',
])
def test_unrecognized_row_structure_is_retained_with_warning(tmp_path, cell):
    path = tmp_path / 'paper.tex'
    path.write_text(table_source(cell))
    plan = apply_layout(tmp_path, {'columns': 'single', 'max_table_rows': 4})
    assert cell in path.read_text()
    assert path.read_text().count('\\begin{table}') == 1
    assert any(item['code'] == 'custom_table_row_limit_unapplied'
               for item in plan['warnings'])


@pytest.mark.parametrize('separator', [r'\\*', r'\\[3pt]', r'\tabularnewline'])
def test_custom_row_breaks_are_retained_with_warning(tmp_path, separator):
    path = tmp_path / 'paper.tex'
    original = table_source('first').replace('first & 1 \\\\', 'first & 1 ' + separator)
    path.write_text(original)
    plan = apply_layout(tmp_path, {'columns': 'single', 'max_table_rows': 4})
    assert 'first & 1 ' + separator in path.read_text()
    assert path.read_text().count('\\begin{table}') == 1
    assert any(item['code'] == 'custom_table_row_limit_unapplied'
               for item in plan['warnings'])


def test_multiline_longtable_converts_to_intact_panels(tmp_path):
    cell = r'\shortstack{one\\two\\three\\four\\five}'
    source = table_source(cell).replace('\\usepackage{booktabs}', '\\usepackage{booktabs,longtable}')
    source = source.replace('\\begin{table}\n\\centering\n', '').replace('\\end{table}\n', '')
    source = source.replace('\\begin{tabular}', '\\begin{longtable}').replace('\\end{tabular}', '\\end{longtable}')
    source = source.replace('\\midrule\n', '\\midrule\n\\endhead\n\\bottomrule\n\\endfoot\n')
    source = source.replace('\\bottomrule\n\\end{longtable}', '\\end{longtable}')
    source = source.replace('\\caption{Synthetic values.}\n', '')
    path = tmp_path / 'paper.tex'
    path.write_text(source)
    plan = apply_layout(tmp_path, {'columns': 'double', 'max_table_rows': 4})
    assert path.read_text().count('\\begin{tabular}') == 2
    assert path.read_text().count(cell) == 1
    assert [block['rows'] for block in plan['blocks']] == [4, 1]


def test_multiline_table_compiles_before_and_after_reflow(tmp_path):
    compiler = shutil.which('tectonic')
    if compiler is None:
        pytest.skip('Actual Tectonic compiler required')
    cell = r'\shortstack{one\\two\\three\\four\\five}'
    path = tmp_path / 'paper.tex'
    path.write_text(table_source(cell))
    for reflow in (False, True):
        if reflow:
            apply_layout(tmp_path, {'columns': 'single', 'max_table_rows': 4})
        result = subprocess.run([compiler, '--keep-logs', 'paper.tex'],
                                cwd=tmp_path, capture_output=True, text=True, timeout=120)
        phase = 'after reflow' if reflow else 'before reflow'
        assert result.returncode == 0, phase + ': ' + result.stdout + result.stderr
        assert (tmp_path / 'paper.pdf').read_bytes().startswith(b'%PDF-')
