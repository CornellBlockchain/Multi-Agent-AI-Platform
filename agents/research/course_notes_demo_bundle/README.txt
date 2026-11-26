COURSE NOTES SEARCH - SHAREABLE FILE-BASED DEMO

This package contains three ORIGINAL, synthetic Markdown lecture-note files:
  course_notes_demo/01_machine_learning.md
  course_notes_demo/02_computer_networks.md
  course_notes_demo/03_databases.md
and a manual script check_course_notes_demo.py.

PURPOSE
Check that Team A Course Notes Search reads real on-disk files, retrieves passages
for different questions, attributes them to filenames with null URLs, handles no
matches, and emits matching start/terminal events. These are sample files, NOT
actual course handoff materials; final evaluation on the team's chosen notes
collection is still required.

INSTALL
1. Unzip package.
2. Copy the folder course_notes_demo/ and the script check_course_notes_demo.py
   directly into agents/research/ in your local project.
3. In your research virtual environment, run:
       cd agents/research
       python check_course_notes_demo.py

The script sets COURSE_NOTES_DIR just for this process and does not read/modify
.env. It should not require any API keys or network access.

EXPECTED
Six PASS messages and the final message 'All six demo checks passed.'
If any assertion fails, inspect how the current course_notes.py ranks passages
or whether its function signatures have changed; adjust the demo to match the
actual implementation rather than changing the tool solely to pass a sample.

IMPORTANT
No private class notes are included. Check your team's permission before
committing any actual course documents. This fixture can be shared as sample data.
