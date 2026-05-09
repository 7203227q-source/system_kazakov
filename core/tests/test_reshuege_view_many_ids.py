from core.services_reshuege import extract_view_many_ids


def test_extract_view_many_ids_prefers_prob_nums():
    html = """
    <div class="prob_nums">Тип 7&nbsp;№&nbsp;<a href="/problem?id=26900">26900</a></div>
    <span id="likes_26900_short"><a href="/problem?id=16125">16125</a></span>
    <div class="prob_nums">Тип 7&nbsp;№&nbsp;<a href="/problem?id=26901">26901</a></div>
    <span id="likes_26901_short"><a href="/problem?id=16143">16143</a></span>
    """
    assert extract_view_many_ids(html) == ["26900", "26901"]


def test_extract_view_many_ids_fallback_when_no_prob_nums():
    html = """
    <a href="/problem?id=100">100</a>
    <a href="/problem?id=101">101</a>
    """
    assert extract_view_many_ids(html) == ["100", "101"]
