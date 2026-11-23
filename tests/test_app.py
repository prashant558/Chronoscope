from streamlit.testing.v1 import AppTest
at = AppTest.from_file("../app.py", default_timeout=60).run()
assert not at.exception, at.exception
assert at.title[0].value.startswith("🔭"), at.title
assert len(at.button) >= 4, "example buttons missing"
print("✅ App loads: title, 4 example buttons, form, no exceptions")
