# Tests for which cut and bar a verdict is taken against. Plain asserts, no test dependency.
# Usage: ~/.cache/humanize/venv/bin/python detect_test.py
import http.client
import json
import math
import os
import re
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "plugin", "skills", "humanize-ai", "scripts")
sys.path.insert(0, SCRIPTS)
import detect as D  # noqa: E402

POOLED = {"threshold_ai": 0.5, "threshold_human": 0.315, "human_reference": [0.0, 0.5, 1.0],
          "registers": {"news": {"threshold_ai": 0.79, "threshold_human": 0.70, "human_reference": [0.1, 0.7, 1.0], "humans": 93},
                        "literary": {"threshold_ai": 0.24, "threshold_human": 0.16, "human_reference": [0.0, 0.1, 0.9], "humans": 90}}}
SENTENCE = "The meeting ran late and the room was too warm for anyone to think clearly about it. "
TEXT = SENTENCE * 8
LONG = SENTENCE * 60


class Stub:
    # stands in for the language models: the blend below ignores every feature, so the score is fixed
    heldout = None

    def lm(self, flat):
        return {"top1_frac": 0.0}, []


class Second(Stub):
    # stands in for the RoBERTa second opinion, reading its number off a marker in the section
    heldout = True

    def heldout_prob(self, flat):
        return 0.9 if "flagthis" in flat else 0.1


SHORT = "flagthis " + SENTENCE * 5   # 86 words: long enough for a verdict, too short to count
COUNTS = SENTENCE * 8                # 136 words


def with_second_opinion(sections):
    # the sectioning is fixed by hand because what is under test is which sections the aggregate reads,
    # not how a particular document happens to split
    blend = {"features": ["mattr"], "coef": [0.0], "mean": [0.0], "scale": [1.0], "intercept": 0.0,
             "human_reference": [i / 100 for i in range(101)], "sentence_min_words": 12,
             "sentence_binoculars_cut": None, "flag_support": {},
             **{k: v for k, v in POOLED.items() if k != "human_reference"}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"prose": blend}, f)
    kept_blend, D.BLEND_FILE = D.BLEND_FILE, f.name
    kept_split, D.doc_sections = D.doc_sections, lambda prose, size=None: sections
    try:
        return D.analyse_document("\n\n".join(sections), Second(), heldout=True, genre="prose")
    finally:
        D.BLEND_FILE, D.doc_sections = kept_blend, kept_split
        os.unlink(f.name)


def test_the_second_opinion_is_read_off_the_sections_that_decide():
    # references/metrics.md measures this detector per text; the document value used to be a max over every
    # section, so one section too short to carry a verdict could set the number for the whole document
    result = with_second_opinion([COUNTS, SHORT])
    assert result["document"] and len(result["sections"]) == 2, result
    assert [s["words"] for s in result["sections"]] == [136, 86], result["sections"]
    assert result["heldout_roberta"] == 0.1, result["heldout_roberta"]
    # the section keeps its own reading, so nothing is hidden from a reader
    assert result["sections"][1]["heldout_roberta"] == 0.9, result["sections"][1]


def test_a_section_that_decides_still_sets_the_second_opinion():
    assert with_second_opinion(["flagthis " + SENTENCE * 8, COUNTS])["heldout_roberta"] == 0.9


def test_when_no_section_is_long_enough_the_short_ones_are_read_after_all():
    # counted falls back to every scored section rather than reporting nothing
    result = with_second_opinion([SHORT, SENTENCE * 5])
    assert [s["words"] for s in result["sections"]] == [86, 85], result["sections"]
    assert result["heldout_roberta"] == 0.9, result["heldout_roberta"]


def test_a_document_with_nothing_long_enough_to_judge_reports_no_second_opinion():
    # every section is under the 80 words a verdict needs, so there is nothing to read it off. Maxing
    # over the sections regardless would be a number about text the verdict itself refused to judge.
    result = with_second_opinion(["flagthis " + SENTENCE * 3, SENTENCE * 3, SENTENCE * 3])
    assert "verdict" not in result or result["verdict"] == "known text", result
    assert "heldout_roberta" not in result, result
    assert result["sections"][0]["heldout_roberta"] == 0.9, result["sections"][0]


def scored(prob, register, text=TEXT):
    blend = {"features": ["mattr"], "coef": [0.0], "mean": [0.0], "scale": [1.0],
             "intercept": math.log(prob / (1 - prob)), "human_reference": [i / 100 for i in range(101)],
             "sentence_min_words": 12, "sentence_binoculars_cut": None, "flag_support": {},
             **{k: v for k, v in POOLED.items() if k != "human_reference"}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"prose": blend}, f)
    kept, D.BLEND_FILE = D.BLEND_FILE, f.name
    try:
        return D.analyse_document(text, Stub(), genre="prose", register=register)
    finally:
        D.BLEND_FILE = kept
        os.unlink(f.name)


def test_a_named_register_brings_its_own_cut_and_bar():
    bars = D.blend_bars(POOLED, "news")
    assert bars["threshold_ai"] == 0.79, bars
    assert bars["threshold_human"] == 0.70, bars


def test_the_reference_the_percentile_is_read_off_moves_with_the_register():
    assert D.blend_bars(POOLED, "literary")["human_reference"] == [0.0, 0.1, 0.9]
    assert D.blend_bars(POOLED, None)["human_reference"] == [0.0, 0.5, 1.0]


def test_no_register_means_the_pooled_pair():
    bars = D.blend_bars(POOLED, None)
    assert (bars["threshold_ai"], bars["threshold_human"]) == (0.5, 0.315), bars


def test_a_register_with_no_cut_fitted_falls_back_rather_than_failing():
    # blog posts, cover letters and talk abstracts have no human writing in the set
    bars = D.blend_bars(POOLED, "blog")
    assert (bars["threshold_ai"], bars["threshold_human"]) == (0.5, 0.315), bars


def test_a_blend_from_before_registers_still_scores():
    old = {"threshold_ai": 0.5, "threshold_human": 0.315}
    assert D.blend_bars(old, "news")["threshold_ai"] == 0.5


def test_a_register_cut_is_what_decides_ai():
    # 0.6 is AI against the pooled cut and ordinary news writing against the news one
    news, pooled = {"prose": D.blend_bars(POOLED, "news")}, {"prose": D.blend_bars(POOLED, None)}
    assert D.text_verdict({"prose": 0.6}, pooled) == "ai"
    assert D.text_verdict({"prose": 0.6}, news) == "human"
    assert D.text_verdict({"prose": 0.75}, news) == "unclear"
    assert D.text_verdict({"prose": 0.8}, news) == "ai"


def test_a_lower_register_cut_flags_what_the_pooled_one_lets_through():
    # 0.3 reads human pooled, because the pooled bar is set by registers that score higher
    literary = {"prose": D.blend_bars(POOLED, "literary")}
    assert D.text_verdict({"prose": 0.3}, literary) == "ai"
    assert D.text_verdict({"prose": 0.3}, {"prose": D.blend_bars(POOLED, None)}) == "human"
    assert D.text_verdict({"prose": 0.2}, literary) == "unclear"


def test_reading_human_is_judged_against_the_register_too():
    news = {"prose": D.blend_bars(POOLED, "news")}
    assert D.text_verdict({"prose": 0.4}, news) == "human"
    assert D.text_verdict({"prose": 0.4}, {"prose": D.blend_bars(POOLED, None)}) == "unclear"


def test_with_two_blends_either_can_say_ai():
    bars = {"prose": D.blend_bars(POOLED, None), "docs": {"threshold_ai": 0.5, "threshold_human": 0.1}}
    assert D.text_verdict({"prose": 0.2, "docs": 0.9}, bars) == "ai"
    assert D.text_verdict({"prose": 0.6, "docs": 0.1}, bars) == "ai"


def test_with_two_blends_both_have_to_say_human():
    bars = {"prose": D.blend_bars(POOLED, None), "docs": {"threshold_ai": 0.5, "threshold_human": 0.1}}
    assert D.text_verdict({"prose": 0.2, "docs": 0.05}, bars) == "human"
    assert D.text_verdict({"prose": 0.2, "docs": 0.2}, bars) == "unclear"


def test_every_register_the_cli_takes_is_one_the_fit_can_produce():
    sys.path.insert(0, os.path.join(HERE, "..", "bench"))
    import fit as F

    assert set(F.REGISTER_OF.values()) == set(D.REGISTERS), (set(F.REGISTER_OF.values()), set(D.REGISTERS))


def test_the_live_blend_carries_a_cut_for_every_register_the_cli_takes():
    # without them --register is accepted and silently does nothing, so a blend from before the cuts
    # (a rollback, or a fit.py that stopped writing them) has to show up here
    fitted = D.load_blends("prose")["prose"].get("registers", {})
    assert set(fitted) == set(D.REGISTERS), (sorted(fitted), sorted(D.REGISTERS))


def test_the_live_blend_cuts_sit_above_their_bars():
    # a cut under its own bar would call a text ai and human at once
    for genre, blend in D.load_blends("both").items():
        for name, bars in blend.get("registers", {}).items():
            assert bars["threshold_human"] <= bars["threshold_ai"], (genre, name, bars)
            assert 0.0 < bars["threshold_ai"] < 1.0, (genre, name, bars)


def test_a_score_exactly_on_the_cut_is_ai():
    news = {"prose": D.blend_bars(POOLED, "news")}
    assert D.text_verdict({"prose": 0.79}, news) == "ai"
    assert D.text_verdict({"prose": 0.5}, {"prose": D.blend_bars(POOLED, None)}) == "ai"


def test_a_score_exactly_on_the_bar_is_not_human_yet():
    news = {"prose": D.blend_bars(POOLED, "news")}
    assert D.text_verdict({"prose": 0.7}, news) == "unclear"
    assert D.text_verdict({"prose": 0.315}, {"prose": D.blend_bars(POOLED, None)}) == "unclear"


def test_the_register_decides_the_verdict_end_to_end():
    assert scored(0.6, None)["verdict"] == "ai"
    assert scored(0.6, "news")["verdict"] == "human"
    assert scored(0.8, "news")["verdict"] == "ai"
    assert scored(0.3, "literary")["verdict"] == "ai"


def test_the_result_says_which_cut_it_used():
    result = scored(0.6, "news")
    assert result["register"] == "news", result
    assert result["ai_bar"] == 0.79 and result["human_bar"] == 0.7, result
    pooled = scored(0.6, None)
    assert pooled["ai_bar"] == 0.5 and "register" not in pooled, pooled


def test_the_percentile_is_read_off_the_registers_own_writers():
    # 0.6 beats 60 of the 101 pooled reference points and 0 of the news ones
    assert scored(0.6, None)["more_ai_like_than_human_samples"] == "59%"
    assert scored(0.6, "news")["more_ai_like_than_human_samples"] == "33%"


def test_a_document_in_sections_is_judged_by_the_register_too():
    result = scored(0.6, "news", text=LONG)
    assert result["document"] and len(result["sections"]) > 1, result
    assert result["register"] == "news" and result["ai_bar"] == 0.79, result
    assert result["verdict"] == "human", result
    assert scored(0.6, None, text=LONG)["verdict"] == "ai"


def test_a_footnote_whose_text_opens_with_a_label_still_reads():
    # markdown_it 2.2.0 reads "[^1]: Title: words" as a link reference and chokes on the scheme-only URL
    doc = "# Guide\n\nThe setting changes how the page is built, and the note below says where it came from.[^1]\n\n[^1]: TEFCA: A Framework for Public Health Interoperability. NACCHO.\n"
    assert "says where it came from" in D.doc_prose(doc)
    assert "A Framework for Public Health" in D.doc_prose(doc)


def test_markdown_the_parser_cannot_read_is_skipped_not_raised():
    assert D.parse_md("[]:A:") == []


def test_markdown_the_parser_can_read_is_left_alone():
    doc = "# Title\n\nA plain paragraph that the parser has no trouble with at all.\n"
    assert D.parse_md(doc) == D.MD.parse(doc)
    # a footnote that reads fine keeps its marker: only a document that throws takes the retry
    footnoted = "# Title\n\nA paragraph with a note.[^1]\n\n[^1]: A plain note with no label in front of it.\n"
    assert D.parse_md(footnoted) == D.MD.parse(footnoted)


CLOSED = {"the", "and", "a", "to", "of", "it", "is", "can", "be", "will", "you", "this", "if", "or", "with", "so"}


def test_a_text_has_no_drift_from_itself():
    assert D.voice_drift(TEXT, TEXT, CLOSED) == 0.0


def test_drift_is_never_negative():
    other = "You can run it if you want to, and it will be fine with the rest of them. " * 8
    assert D.voice_drift(TEXT, other, CLOSED) > 0
    assert D.voice_drift(other, TEXT, CLOSED) > 0


def test_a_bigger_change_of_function_words_drifts_further():
    near = TEXT.replace("too warm", "so warm")
    far = "You can be sure of it, and if you will run the thing then it is going to be fine with you. " * 8
    assert D.voice_drift(TEXT, near, CLOSED) < D.voice_drift(TEXT, far, CLOSED)


def test_drift_ignores_the_subject_and_reads_the_function_words():
    # same shape, every content word swapped: the skeleton is unchanged, so this is not a move of voice
    same_shape = "The lecture ran long and the hall was too cold for anybody to speak plainly about it. " * 8
    swapped_shape = "The meeting ran late, so the room was warm, and nobody could think about it clearly. " * 8
    assert D.voice_drift(TEXT, same_shape, CLOSED) < D.voice_drift(TEXT, swapped_shape, CLOSED)


def test_drift_is_reported_by_compare_when_a_blend_is_present():
    result = D.compare(TEXT, TEXT)
    # the live blend ships an ngram table; without one the key is simply absent
    if D.load_blends("docs").get("docs", {}).get("ngram"):
        assert result["voice_drift"] == 0.0



def own_client(**extra):
    # what ask_server and start-scorer.sh send
    return {"Host": f"127.0.0.1:{D.PORT}", "Content-Type": "application/json", "Content-Length": "40"} | extra


def test_the_scorer_lets_its_own_clients_in():
    assert D.refuse("/score", own_client()) is None
    assert D.refuse("/score", own_client(Host=f"localhost:{D.PORT}")) is None
    assert D.refuse("/score", own_client(**{"Content-Type": "application/json; charset=utf-8"})) is None
    assert D.refuse("/score", own_client(**{"Content-Length": str(D.MAX_BODY)})) is None


def test_the_scorer_turns_away_what_a_web_page_can_send():
    # a cross-origin form or fetch with a text/plain body needs no preflight, so the browser sends it as is
    assert D.refuse("/score", own_client(Origin="https://evil.example")) == 403
    assert D.refuse("/score", own_client(**{"Content-Type": "text/plain"})) == 415
    assert D.refuse("/score", own_client(**{"Content-Type": "application/x-www-form-urlencoded"})) == 415
    assert D.refuse("/score", {k: v for k, v in own_client().items() if k != "Content-Type"}) == 415
    # DNS rebinding reaches 127.0.0.1 under the attacker's own host name
    assert D.refuse("/score", own_client(Host=f"rebind.evil.example:{D.PORT}")) == 403
    assert D.refuse("/score", own_client(Host="127.0.0.1:1")) == 403
    assert D.refuse("/score", {k: v for k, v in own_client().items() if k != "Host"}) == 403
    assert D.refuse("/other", own_client()) == 404
    assert D.refuse("/score", own_client(**{"Content-Length": str(D.MAX_BODY + 1)})) == 413
    assert D.refuse("/score", own_client(**{"Content-Length": "lots"})) == 400
    # rfile.read(-1) reads to the end, so a negative length would lift the cap
    assert D.refuse("/score", own_client(**{"Content-Length": "-1"})) == 400
    assert D.refuse("/score", {k: v for k, v in own_client().items() if k != "Content-Length"}) == 411


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_the_running_scorer_answers_its_client_and_refuses_a_page():
    kept = D.PORT, D.Scorer, D.analyse_document
    try:
        D.PORT = free_port()
        D.Scorer = lambda heldout=False: None
        D.analyse_document = lambda *args: {"verdict": "human"}
        threading.Thread(target=D.serve, daemon=True).start()
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", D.PORT), timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        assert D.ask_server("hello", False)["verdict"] == "human", "the scorer's own client was refused"
        # a draft over the cap is scored in-process instead of ending the run (or a whole --scan)
        assert D.ask_server("word " * (D.MAX_BODY // 5 + 1), False) is None

        def post(headers, body=b'{"text": "hello"}'):
            conn = http.client.HTTPConnection("127.0.0.1", D.PORT, timeout=10)
            conn.putrequest("POST", "/score", skip_host=True, skip_accept_encoding=True)
            for key, value in (headers | {"Content-Length": str(len(body))}).items():
                conn.putheader(key, value)
            conn.endheaders(body)
            status = conn.getresponse().status
            conn.close()
            return status

        assert post({"Host": f"127.0.0.1:{D.PORT}", "Content-Type": "application/json"}) == 200
        assert post({"Host": f"127.0.0.1:{D.PORT}", "Content-Type": "text/plain", "Origin": "https://evil.example"}) == 403
        assert post({"Host": f"127.0.0.1:{D.PORT}", "Content-Type": "text/plain"}) == 415
        assert post({"Host": f"evil.example:{D.PORT}", "Content-Type": "application/json"}) == 403
    finally:
        D.PORT, D.Scorer, D.analyse_document = kept


def test_setup_downloads_the_model_versions_detect_loads():
    setup = open(os.path.join(SCRIPTS, "setup.sh")).read()
    pinned = dict(re.findall(r'\("([\w./-]+)", "([0-9a-f]{40})"\)', setup))
    assert pinned == D.REVISIONS, pinned
    assert "revision=revision" in setup


def test_the_client_never_sends_a_draft_through_a_proxy():
    # a proxy that keeps whatever reaches it, and no scorer on the port, so the client should fall back
    seen = []
    proxy = socket.socket()
    proxy.bind(("127.0.0.1", 0))
    proxy.listen(1)
    proxy.settimeout(2)

    def accept():
        try:
            conn, _ = proxy.accept()
            seen.append(conn.recv(65536))
            conn.close()
        except OSError:
            pass

    threading.Thread(target=accept, daemon=True).start()
    names = ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")
    kept = D.PORT, {k: os.environ.get(k) for k in names}
    try:
        D.PORT = free_port()
        os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.getsockname()[1]}"
        os.environ.pop("no_proxy", None)
        os.environ.pop("NO_PROXY", None)
        try:
            result = D.ask_server("a private draft", False)
        except SystemExit as stop:
            raise AssertionError(f"the client stopped instead of falling back: {stop}")
        time.sleep(0.2)
        assert result is None
        assert not seen, "the draft went to the proxy"
    finally:
        D.PORT = kept[0]
        for k, v in kept[1].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        proxy.close()


def test_scan_skips_a_symlink_that_points_out_of_the_folder():
    import subprocess
    for use_git in (True, False):
        with tempfile.TemporaryDirectory() as tmp:
            outside = os.path.join(tmp, "secret.txt")
            with open(outside, "w") as f:
                f.write("aws_secret_access_key = do-not-copy-me\n")
            repo = os.path.join(tmp, "repo")
            os.mkdir(repo)
            with open(os.path.join(repo, "README.md"), "w") as f:
                f.write("# Notes\n\nA short readme.\n")
            os.symlink(outside, os.path.join(repo, "notes.txt"))
            if use_git:
                subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
                subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            out = os.path.join(tmp, "scan.json")
            D.scan(repo, False, out, fast=True)
            saved = open(out).read()
            assert "do-not-copy-me" not in saved, f"scan.json carries a file from outside the folder (git={use_git})"
            assert "skipped" in json.loads(saved)["notes.txt"]["error"]
            assert "README.md" in json.loads(saved)


def test_scan_skips_what_is_not_a_regular_file():
    # a named pipe blocks whoever opens it to read, so a scan that opens one never finishes
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "README.md"), "w") as f:
            f.write("# Notes\n\nA short readme.\n")
        os.mkfifo(os.path.join(tmp, "pipe.txt"))
        out = os.path.join(tmp, "scan.json")
        worker = threading.Thread(target=D.scan, args=(tmp, False, out), kwargs={"fast": True}, daemon=True)
        worker.start()
        worker.join(20)
        assert not worker.is_alive(), "the scan hung on a named pipe"
        assert "skipped" in json.load(open(out))["pipe.txt"]["error"]


def test_setup_refuses_an_old_python_and_rebuilds_an_old_venv():
    import shlex
    import shutil
    import subprocess
    setup = os.path.join(SCRIPTS, "setup.sh")
    real = shlex.quote(sys.executable)
    with tempfile.TemporaryDirectory() as home:
        tools = os.path.join(home, "tools")
        os.mkdir(tools)

        def script(name, body):
            p = os.path.join(tools, name)
            with open(p, "w") as f:
                f.write("#!/bin/bash\n" + body)
            os.chmod(p, 0o755)
            return p

        old = script("python-old", '[ "$1" = "--version" ] && { echo "Python 3.9.6"; exit 0; }\nexit 1\n')
        # what a fresh venv holds: its python sends version checks to a real 3.11+ and skips the model download
        made_python = script("made-python", f'[ "$1" = "-c" ] && exec {real} "$@"\ncat > /dev/null\nexit 0\n')
        made_pip = script("made-pip", "exit 0\n")
        new = script("python-new", 'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
                     f'  mkdir -p "$3/bin" && cp {shlex.quote(made_python)} "$3/bin/python" && cp {shlex.quote(made_pip)} "$3/bin/pip"\n'
                     f'  exit 0\nfi\nexec {real} "$@"\n')
        venv = os.path.join(home, ".cache", "humanize", "venv")
        planted = os.path.join(venv, "planted")

        def run(python):
            return subprocess.run(["bash", setup], env={"HOME": home, "PATH": os.environ["PATH"], "PYTHON": python},
                                  capture_output=True, text=True, timeout=60)

        def plant(python, pip=True):
            shutil.rmtree(venv, ignore_errors=True)
            os.makedirs(os.path.join(venv, "bin"))
            shutil.copy(python, os.path.join(venv, "bin", "python"))
            if pip:
                shutil.copy(made_pip, os.path.join(venv, "bin", "pip"))
            open(planted, "w").close()

        done = run(old)
        assert done.returncode == 1 and "3.11 or newer" in done.stderr, done.stderr
        assert not os.path.exists(venv), "a venv was made with a Python that can't install the pins"
        done = run("no-such-python")
        assert done.returncode == 1 and "is missing." in done.stderr and "not found" not in done.stderr, done.stderr

        plant(old)
        done = run(new)
        assert done.returncode == 0 and not os.path.exists(planted), ("the venv from the old Python was reused", done.stderr)
        plant(made_python, pip=False)
        done = run(new)
        assert done.returncode == 0 and not os.path.exists(planted), ("a venv with no pip was reused", done.stderr)
        plant(made_python)
        done = run(new)
        assert done.returncode == 0 and os.path.exists(planted), ("a good venv was rebuilt", done.stderr)


def test_only_a_stranger_on_the_port_gets_the_port_advice():
    import http.server

    class Answer(http.server.BaseHTTPRequestHandler):
        code, body = 500, b"{}"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(self.code)
            self.end_headers()
            self.wfile.write(self.body)

        def log_message(self, *args):
            pass

    kept = D.PORT
    try:
        for code, body, advised in ((500, b'{"server": "humanize", "error": "boom"}', False), (404, b"{}", True)):
            Answer.code, Answer.body = code, body
            server = http.server.HTTPServer(("127.0.0.1", 0), Answer)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            D.PORT = server.server_address[1]
            try:
                D.ask_server("hello", False)
                raise AssertionError("an error reply was taken as a score")
            except SystemExit as stop:
                assert ("HUMANIZE_PORT" in str(stop)) == advised, (code, str(stop))
            finally:
                server.shutdown()
    finally:
        D.PORT = kept


def test_start_scorer_will_not_take_another_apps_port_for_the_scorer():
    import http.server
    import subprocess

    class Answer(http.server.BaseHTTPRequestHandler):
        body = b"{}"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.body)

        def log_message(self, *args):
            pass

    class Proxy(Answer):
        body = b'{"server": "humanize", "verdict": "human"}'

    # the proxy claims to be the scorer, so a script that asked it would wrongly report the scorer running
    proxy = http.server.HTTPServer(("127.0.0.1", 0), Proxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    via = f"http://127.0.0.1:{proxy.server_address[1]}"
    for body, code, said in ((b'{"result": null, "error": "unsupported action"}', 1, "HUMANIZE_PORT"),
                             (b'{"server": "humanize", "verdict": "human"}', 0, "already running")):
        Answer.body = body
        server = http.server.HTTPServer(("127.0.0.1", 0), Answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {k: v for k, v in os.environ.items() if k.lower() != "no_proxy"}
        try:
            done = subprocess.run(["bash", os.path.join(SCRIPTS, "start-scorer.sh")], capture_output=True, text=True, timeout=30,
                                  env=env | {"HUMANIZE_PORT": str(server.server_address[1]), "http_proxy": via, "HTTP_PROXY": via})
        finally:
            server.shutdown()
        assert done.returncode == code and said in done.stdout + done.stderr, (body, done.stdout, done.stderr)
    proxy.shutdown()

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ok   {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
