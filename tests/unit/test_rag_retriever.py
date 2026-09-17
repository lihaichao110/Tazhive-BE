from app.services.rag.retriever import RetrievedChunk, extract_query_keywords, select_final_chunks


def test_extract_keywords_strips_colloquial_wrapper_and_splits_particles():
    assert extract_query_keywords("那你知道信息技术部的李海超么") == ["信息技术部", "李海超"]


def test_extract_keywords_handles_common_question_forms():
    assert extract_query_keywords("你知道李海超么") == ["李海超"]
    assert extract_query_keywords("李海超是谁") == ["李海超"]
    assert extract_query_keywords("帮我查一下王丽丽的分机号") == ["王丽丽", "分机号"]
    assert extract_query_keywords("查一下张三和李四的邮箱") == ["张三", "李四", "邮箱"]


def test_extract_keywords_keeps_english_and_number_runs():
    keywords = extract_query_keywords("lihaichao@cathaylife.cn 的邮箱")

    assert sorted(keywords) == ["cathaylife", "lihaichao", "邮箱"]


def test_extract_keywords_returns_empty_for_short_or_none_input():
    assert extract_query_keywords("") == []
    assert extract_query_keywords("hi") == []
    assert extract_query_keywords("？") == []


def test_select_final_keeps_lexical_hits_regardless_of_similarity():
    lexical = RetrievedChunk(content="李海超的记录", similarity=0.30, id="a")
    vector = RetrievedChunk(content="高分向量记录", similarity=0.60, id="b")

    final = select_final_chunks([lexical, vector], lexical_ids={"a"}, top_k=5, score_threshold=0.4)

    assert [c.id for c in final] == ["a", "b"]


def test_select_final_drops_vector_candidates_below_threshold():
    low = RetrievedChunk(content="低分向量记录", similarity=0.30, id="a")
    high = RetrievedChunk(content="高分向量记录", similarity=0.50, id="b")

    final = select_final_chunks([low, high], lexical_ids=set(), top_k=5, score_threshold=0.4)

    assert [c.id for c in final] == ["b"]


def test_select_final_truncates_to_top_k_and_allows_disabled_threshold():
    chunks = [RetrievedChunk(content=f"记录{i}", similarity=0.1, id=str(i)) for i in range(8)]

    final = select_final_chunks(chunks, lexical_ids=set(), top_k=3, score_threshold=None)

    assert [c.id for c in final] == ["0", "1", "2"]
