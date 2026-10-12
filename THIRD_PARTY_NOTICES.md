# License scope and third-party packages

The root MIT LICENSE applies to the self-authored source, documentation, synthetic fixture generator and original report layout in this public repository. Its attribution currently uses “AssayPilot contributors”; the project owner can replace it with their preferred author name before publishing.

No enterprise template, corporate logo, interview document or real experimental dataset is distributed. The synthetic CSV/XLSX files are generated from the equations in `tools/generate_sample.py`. No third-party font or runtime binary is bundled.

Dependencies retain their own licenses; the project's MIT license does not replace them. Exact versions are recorded in the lock files. Before redistributing an installed environment, review the dependency license notices.

| Component | Upstream license information |
|---|---|
| NumPy | https://github.com/numpy/numpy/blob/main/LICENSE.txt |
| SciPy | https://github.com/scipy/scipy/blob/main/LICENSE.txt |
| Matplotlib | https://matplotlib.org/stable/project/license.html |
| openpyxl | https://foss.heptapod.net/openpyxl/openpyxl |
| python-docx | https://github.com/python-openxml/python-docx/blob/master/LICENSE |
| lxml | https://lxml.de/FAQ.html#what-license-does-lxml-use |
| Pillow | https://github.com/python-pillow/Pillow/blob/main/LICENSE |
| defusedxml | https://github.com/tiran/defusedxml |
| Optional PyMuPDF | https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright |

PyMuPDF is an optional PDF reader and has AGPL/commercial licensing terms. It is kept in `requirements-pdf.txt` and its separate lock file, outside the default runtime installation. Check those terms before enabling it for a deployment or redistributing the dependency. The default app can analyze, export and read public HTML without this optional package.
