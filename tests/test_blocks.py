from textwrap import dedent

from code_complexity_py.blocks import extract_blocks


def test_top_level_function():
    src = "def foo():\n    return 1\n"
    assert [b.name for b in extract_blocks(src)] == ["foo"]


def test_method_named_with_class_prefix():
    src = dedent(
        """\
        class Foo:
            def bar(self):
                return 1
            def baz(self):
                return 2
        """
    )
    names = [b.name for b in extract_blocks(src)]
    assert names == ["Foo.bar", "Foo.baz"]


def test_no_class_row_is_emitted():
    src = "class Foo:\n    def bar(self): return 1\n"
    names = [b.name for b in extract_blocks(src)]
    assert "Foo" not in names
    assert names == ["Foo.bar"]


def test_nested_function_uses_dot_notation():
    src = dedent(
        """\
        def outer():
            def inner():
                return 1
            return inner()
        """
    )
    names = [b.name for b in extract_blocks(src)]
    assert names == ["outer", "outer.inner"]


def test_method_inside_nested_class():
    src = dedent(
        """\
        class Outer:
            class Inner:
                def deep(self):
                    return 1
        """
    )
    assert [b.name for b in extract_blocks(src)] == ["Outer.Inner.deep"]


def test_async_def_emitted():
    src = "async def fetch():\n    return 1\n"
    assert [b.name for b in extract_blocks(src)] == ["fetch"]


def test_syntax_error_returns_empty():
    assert extract_blocks("def (:\n") == []


def test_line_ranges_reasonable():
    src = dedent(
        """\
        def a():
            return 1


        def b():
            return 2
        """
    )
    bs = extract_blocks(src)
    assert bs[0].name == "a" and bs[0].start == 1 and bs[0].end == 2
    assert bs[1].name == "b" and bs[1].start == 5 and bs[1].end == 6
