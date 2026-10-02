"""The C++ dictionary-read scan: what an OpenFOAM-based solver's own source
reads, and where.

For every read (``get<T>``, ``getOrDefault``, ``lookupOrDefault``,
``lookup``, ``readScalar``/``readLabel``/``readBool``, ``readEntry``,
``readIfPresent``, ``found``, ``isDict``, ``subDict``, ``subOrEmptyDict``,
``optionalSubDict``, ``findDict``, the ``dimensioned<T>`` constructors) the
scan records the key, the method, the type, the default literal, the
sub-dictionary scope below a root (a function parameter, a member, ``this``
or a literal ``IOdictionary`` document), the source location, and the
selection-table names of the class it is read in. It also records which
dictionary each call passes to which parameter, so a root's place in a
document can be found from the catalogue (``locate``). What it cannot
resolve it reports as unresolved (``None``); it never guesses.

The scan is a pure function of the ``*.C``/``*.H`` files and of this
scanner, so it is cached by their content digest (``cached_scan``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

from omnidriver.core.contracts.catalogue_paths import catalogued_paths

from . import rtst_scanner
from .rtst_scanner import scan_rtst_registrations

#: One subDict segment the C++ names by an expression, not a literal: any
#: name, the way a catalogue's ``<name>`` placeholder is.
ANY_SEGMENT = "*"

_KEY_METHODS = {
    "get", "getCheck", "lookup", "readEntry", "getOrDefault", "lookupOrDefault",
    "getCheckOrDefault", "getOrAdd", "lookupOrAddDefault", "readIfPresent", "found", "isDict",
}
_SUBDICT_METHODS = {"subDict", "subOrEmptyDict", "optionalSubDict", "findDict"}
_WRAPPERS = {"readScalar": "scalar", "readLabel": "label", "readBool": "bool", "readInt": "label", "readWord": "word"}
#: Methods that test for a key rather than read its value.
_PROBES = {"found", "isDict", "findDict"}
_ENUM_METHODS = {"get", "getOrDefault", "lookupOrDefault", "readEntry"}

_INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', re.MULTILINE)
_PREPROCESSOR = re.compile(r"^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", re.MULTILINE)
_STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')
_IDENT = re.compile(r"[A-Za-z_]\w*")
_METHOD_NAMES = "|".join(sorted(_KEY_METHODS | _SUBDICT_METHODS, key=len, reverse=True))
_TEMPLATE_ARGS = r"(?P<targs><[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?"
_METHOD_CALL = re.compile(r"(?:\.|->)\s*(?P<method>" + _METHOD_NAMES + r")\b\s*" + _TEMPLATE_ARGS + r"\s*\(")
_BARE_CALL = re.compile(r"(?<![\w.>:])(?P<method>" + _METHOD_NAMES + r")\b\s*" + _TEMPLATE_ARGS + r"\s*\(")
_DIMENSIONED = re.compile(
    r"\b(?P<type>dimensioned(?:Scalar|Vector|Tensor|SymmTensor)|dimensioned\s*<\s*\w+\s*>)"
    r"(?:\s+\w+)?\s*\((?=\s*\")"
)
_MEMBER_INIT = re.compile(r"(?<![\w.>:])(?P<member>[A-Za-z_]\w*)\s*\((?=\s*\")")
#: Any call: ``name(``, ``Qual::name(``, ``.name(``, ``->name(``.
_CALL = re.compile(r"(?P<callee>(?:[A-Za-z_]\w*\s*::\s*)*[A-Za-z_]\w*)\s*\(")
_NUMBER = re.compile(r"\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*")
_DECLARED_WRAPPER = re.compile(r"\b(?P<type>[A-Za-z_][\w:]*(?:<[^<>;()]*>)?)\s+[A-Za-z_]\w*\s*[({]\s*$")
_FUNCTIONAL_CAST = re.compile(r"\b(?P<type>word|Switch|scalar|label|bool|fileName|vector|point|tensor)\s*\(\s*$")
_DICT_DECL = re.compile(
    r"\b(?:const\s+)?(?:Foam::)?(?P<type>IOdictionary|dictionary)\s*[&*]?\s*(?P<name>[A-Za-z_]\w*)\s*(?P<op>=|\(|\{)"
)
_DICT_PARAM = re.compile(r"\b(?:Foam::)?(?:IO)?dictionary\s*[&*]?\s*(?P<name>[A-Za-z_]\w*)\s*(?:=|$)")
_ENTRY_DECL = re.compile(r"\b(?:const\s+)?(?:Foam::)?entry\s*&\s*(?P<name>[A-Za-z_]\w*)\s*(?P<op>=|:)")
_KEYWORDS = frozenset({
    "return", "delete", "new", "else", "case", "goto", "throw", "using", "typedef", "operator", "const",
    "if", "while", "for", "switch", "do", "sizeof", "public", "private", "protected", "template",
    "typename", "class", "struct", "namespace", "static", "virtual", "inline", "friend", "explicit",
})
_DECLARATION = re.compile(
    r"(?:^|(?<=[;{}(,\n]))\s*(?:(?:const|static|mutable|volatile)\s+)*"
    r"(?P<type>(?:Foam::)?[A-Za-z_]\w*(?:\s*<[^;{}()]*>)?(?:::[A-Za-z_]\w*)*)\s*[&*]{0,2}\s*"
    r"(?P<name>[A-Za-z_]\w*)\s*(?=[;=({,)\[])"
)
_FOR_ALL = re.compile(r"\bforAll(?:Const)?Iters?\s*\(\s*(?:\w+\s*,\s*)?(?P<expr>[^,()]+(?:\([^()]*\))?)\s*,\s*(?P<iter>\w+)\s*\)")
_CLASS_HEAD = re.compile(r"\b(?:class|struct)\s+(?P<name>[A-Za-z_]\w*)\s*(?:final\s*)?(?::(?P<bases>[^{]*))?$")
_TEMPLATE_PREFIX = re.compile(r"^\s*template\s*<")
_DICTIONARY_BASES = {"dictionary", "IOdictionary"}
_NOT_A_CALL = {"if", "for", "while", "switch", "return", "sizeof", "catch", "defined"}


@dataclass(frozen=True)
class DictRead:
    """One dictionary read. ``root`` names the dictionary the read starts
    from (``param:<function>:<name>``, ``member:<class>:<name>``,
    ``this:<class>`` or ``document:<name>``) and ``scope`` the
    sub-dictionaries below it; both are ``None`` when the receiver is not
    resolved. ``key`` is ``None`` when the C++ names the key by an
    expression."""

    key: str | None
    method: str
    type: str | None
    default: str | None
    scope: tuple[str, ...] | None
    root: str | None
    file: str
    line: int
    function: str | None
    selected_as: tuple[tuple[str, str], ...] = ()

    @property
    def subdict(self) -> bool:
        return self.method in _SUBDICT_METHODS

    @property
    def value_read(self) -> bool:
        return self.key is not None and self.scope is not None and self.method not in _PROBES | _SUBDICT_METHODS


@dataclass(frozen=True)
class Scan:
    """Every read, selection-table registration and dictionary-passing
    call under one source tree, at one content ``digest``."""

    digest: str
    reads: tuple[DictRead, ...]
    #: ``{base: {registered name: derived class}}``.
    registrations: dict[str, dict[str, str]]
    #: ``(function, index, parameter count, root)`` per dictionary parameter.
    parameters: tuple[tuple[str, int, int, str], ...] = ()
    #: ``(callee, argument index, argument count, root, scope)`` per call
    #: passing a resolved dictionary; a callee ``=<root>`` is a member
    #: initialised from it, ``^<class>`` a base-class constructor.
    calls: tuple[tuple[str, int, int, str, tuple[str, ...]], ...] = ()

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, payload: dict) -> "Scan":
        def tupled(value):
            return tuple(tupled(item) for item in value) if isinstance(value, list) else value

        reads = tuple(DictRead(**{key: tupled(value) for key, value in read.items()}) for read in payload["reads"])
        return cls(
            digest=payload["digest"], reads=reads, registrations=payload["registrations"],
            parameters=tupled(payload["parameters"]), calls=tupled(payload["calls"]),
        )

    def resolution(self) -> dict[str, object]:
        """How much of the scan resolved, measured on its own reads."""
        reads = [read for read in self.reads if not read.subdict]
        values = [read for read in reads if read.method not in _PROBES]
        total = len(reads) or 1
        return {
            "reads": len(reads),
            "subdict_reads": len(self.reads) - len(reads),
            "literal_key": round(100 * sum(r.key is not None for r in reads) / total, 1),
            "resolved_scope": round(100 * sum(r.scope is not None for r in reads) / total, 1),
            "resolved_type": round(100 * sum(r.type is not None for r in values) / (len(values) or 1), 1),
            "selected_class": round(100 * sum(bool(r.selected_as) for r in reads) / total, 1),
        }


def source_files(source_root: Path) -> Iterator[Path]:
    """The ``*.C``/``*.H`` files a scan reads, in a stable order; wmake's
    ``lnInclude`` links and ``Make`` products are not source."""
    for path in sorted(Path(source_root).rglob("*")):
        if path.suffix in {".C", ".H"} and path.is_file() and not {"lnInclude", "Make"} & set(path.parts):
            yield path


def source_digest(source_root: Path) -> str:
    """The cache key: the scanner's own modules and every source file."""
    digest = hashlib.sha256()
    for module in (Path(__file__), Path(rtst_scanner.__file__)):
        digest.update(module.read_bytes())
    for path in source_files(source_root):
        digest.update(path.relative_to(source_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


_MEMO: dict[tuple[str, str], Scan] = {}


def cached_scan(source_root: Path, *, cache_root: Path | None, force: bool = False) -> Scan:
    """The scan of ``source_root``. Only the digest is recomputed unless the
    source or the scanner changed; ``cache_root`` (the supplied scratch
    root) keeps the scan across processes, and ``force`` rescans. A cache
    file that cannot be read is rescanned and rewritten."""
    source_root = Path(source_root).resolve()
    digest = source_digest(source_root)
    key = (str(source_root), digest)
    cache_file = Path(cache_root) / "cxx-scan" / f"{digest}.json" if cache_root is not None else None
    scan = None if force else _MEMO.get(key)
    if scan is not None and (cache_file is None or cache_file.is_file()):
        return scan
    if scan is None and not force and cache_file is not None:
        scan = _load(cache_file, digest)
        if scan is not None:
            _MEMO[key] = scan
            return scan
    if scan is None:
        scan = scan_source(source_root, digest=digest)
    _MEMO[key] = scan
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = scan.to_json()
        with tempfile.NamedTemporaryFile("w", dir=cache_file.parent, suffix=".tmp", delete=False) as handle:
            json.dump({**payload, "checksum": _checksum(payload)}, handle)
        os.replace(handle.name, cache_file)
    return scan


def _checksum(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _load(cache_file: Path, digest: str) -> Scan | None:
    """The cached scan, or ``None`` when the file is unreadable, altered or
    for another digest."""
    try:
        payload = json.loads(cache_file.read_text())
        checksum = payload.pop("checksum")
        scan = Scan.from_json(payload)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return scan if scan.digest == digest and checksum == _checksum(payload) else None


def scan_source(source_root: Path, *, digest: str | None = None) -> Scan:
    source_root = Path(source_root)
    files: dict[str, tuple[str, str, list[_Function]]] = {}
    includes: dict[str, list[tuple[str, int]]] = {}
    for path in source_files(source_root):
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = _strip_comments(raw)
        structure = _structure(text)
        relative = path.relative_to(source_root).as_posix()
        files[relative] = (text, structure, list(_functions(structure)))
        includes[relative] = [(m.group(1), m.start()) for m in _INCLUDE.finditer(raw)]
    classes = _class_index(structure for _text, structure, _functions_ in files.values())
    registrations = scan_rtst_registrations({relative: text for relative, (text, _s, _f) in files.items()})
    selected: dict[str, list[tuple[str, str]]] = {}
    for base, names in registrations.items():
        for name, derived in names.items():
            selected.setdefault(derived, []).append((base, name))
    reads: list[DictRead] = []
    parameters: set[tuple[str, int, int, str]] = set()
    calls: list[tuple[str, int, int, str, tuple[str, ...]]] = []
    for relative, (text, structure, functions) in files.items():
        for function in functions or _includers(relative, files, includes):
            params = _split_args(function.params)
            for index, param in enumerate(params):
                match = _DICT_PARAM.search(param)
                if match:
                    parameters.add((function.name, index, len(params), f"param:{function.name}:{match.group('name')}"))
            reads.extend(_reads_in(text, structure, function, relative, classes, selected, calls))
    return Scan(
        digest=digest or source_digest(source_root), reads=tuple(reads), registrations=registrations,
        parameters=tuple(sorted(parameters)), calls=tuple(calls),
    )


def _includers(relative: str, files, includes) -> list["_Function"]:
    """A function-less fragment ``#include``d inside function bodies (an
    OpenFOAM idiom) is read as part of the including function."""
    basename = relative.rsplit("/", 1)[-1]
    if sum(1 for other in files if other.rsplit("/", 1)[-1] == basename) != 1:
        return []
    text = files[relative][0]
    for includer, directives in includes.items():
        for name, position in directives:
            if name.rsplit("/", 1)[-1] != basename:
                continue
            host = next((f for f in files[includer][2] if f.start <= position <= f.end), None)
            if host is not None:
                return [_Function(host.name, host.owner, host.params, 0, len(text))]
    return []


# -- text preparation --------------------------------------------------------

def _mask(match: re.Match[str]) -> str:
    return "".join(c if c in "\r\n" else " " for c in match.group())


def _strip_comments(text: str) -> str:
    """Comments and preprocessor lines blanked in place, so offsets and line
    numbers survive. String literals are skipped first so a ``//`` inside
    one is not taken for a comment."""
    out, pos = [], 0
    token = re.compile(r'"(?:\\.|[^"\\\n])*"|/\*.*?\*/|//[^\n]*', re.DOTALL)
    for match in token.finditer(text):
        out.append(text[pos:match.start()])
        out.append(match.group() if match.group().startswith('"') else _mask(match))
        pos = match.end()
    out.append(text[pos:])
    return _PREPROCESSOR.sub(_mask, "".join(out))


def _structure(text: str) -> str:
    """``text`` with string contents blanked, for brace and paren matching."""
    return _STRING.sub(lambda m: '"' + " " * (len(m.group()) - 2) + '"', text)


def _close(text: str, open_at: int) -> int:
    """Index of the bracket closing the one at ``open_at`` (-1 if none)."""
    pairs = {"(": ")", "[": "]", "{": "}", "<": ">"}
    opener = text[open_at]
    closer, depth = pairs[opener], 0
    for index in range(open_at, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_args(text: str) -> list[str]:
    args, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail or args:
        args.append(tail)
    return args


def _literal(arg: str) -> str | None:
    match = re.fullmatch(r'\s*"((?:\\.|[^"\\])*)"\s*', arg)
    return match.group(1) if match else None


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _strip_template_args(name: str) -> str:
    out, depth = [], 0
    for char in name:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif depth == 0:
            out.append(char)
    return "".join(out).replace(" ", "")


# -- structure: classes and functions ---------------------------------------

@dataclass(frozen=True)
class _Class:
    bases: tuple[str, ...] = ()
    #: Members and no-argument methods declared as ``dictionary``.
    dictionaries: frozenset[str] = frozenset()
    #: Members declared with any other type.
    others: frozenset[str] = frozenset()
    #: ``dimensioned<T>`` members, by name: constructed from a dictionary
    #: in an initialiser list (``c0_("c0", dict)``).
    dimensioned: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _Function:
    name: str
    owner: str | None
    params: str
    start: int
    end: int


_DICT_MEMBER = re.compile(
    r"\b(?:const\s+)?(?:Foam::)?(?:IO)?dictionary\s*[&*]?\s*(?P<name>[A-Za-z_]\w*)\s*(?:;|\(\s*\)\s*(?:const\s*)?[;{])"
)


def _class_index(structures: Iterable[str]) -> dict[str, _Class]:
    """Every class head in the tree: its bases and the dictionaries it
    declares (members, and accessors such as ``coeffDict()``)."""
    index: dict[str, _Class] = {}
    for structure in structures:
        for brace in re.finditer(r"\{", structure):
            match = _CLASS_HEAD.search(_drop_template_prefix(_head_before(structure, brace.start())))
            if match is None or re.search(r"\benum\b", _head_before(structure, brace.start())):
                continue
            bases = tuple(
                _strip_template_args(re.sub(r"\b(public|protected|private|virtual)\b", "", base)).split("::")[-1]
                for base in _split_args(match.group("bases") or "") if base.strip()
            )
            close_at = _close(structure, brace.start())
            body = structure[brace.start():close_at if close_at > 0 else len(structure)]
            members = frozenset(found.group("name") for found in _DICT_MEMBER.finditer(body))
            others = frozenset(
                found.group("name") for found in _DECLARATION.finditer(body)
                if _declares_other(found) and body[found.end():].lstrip().startswith(";")
            )
            dimensioned = tuple(
                (found.group("name"), re.sub(r"\s+", "", found.group("type")).replace("Foam::", ""))
                for found in _DECLARATION.finditer(body)
                if found.group("type").replace("Foam::", "").startswith("dimensioned")
            )
            known = index.get(match.group("name"), _Class())
            index[match.group("name")] = _Class(
                known.bases + bases, known.dictionaries | members, known.others | (others - members),
                known.dimensioned + dimensioned,
            )
    return index


def _declares_other(match: re.Match[str]) -> bool:
    kind = _strip_template_args(match.group("type")).split("::")[-1]
    return kind not in _KEYWORDS and kind not in _DICTIONARY_BASES | {"entry", "auto"} and match.group("name") not in _KEYWORDS


def _lineage(name: str | None, classes: dict[str, _Class], seen: tuple[str, ...] = ()) -> Iterator[str]:
    if name is None or name in seen:
        return
    yield name
    for base in classes.get(name, _Class()).bases:
        yield from _lineage(base, classes, seen + (name,))


def _head_start(structure: str, brace: int) -> int | None:
    """Where the statement a ``{`` opens starts: after the last ``;``, ``{``
    or ``}`` outside parentheses. ``None`` when the brace sits inside an
    open parenthesis (a braced initialiser in an argument list)."""
    depth = 0
    for index in range(brace - 1, -1, -1):
        char = structure[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth < 0:
                return None
        elif char in ";{}" and depth == 0:
            return index + 1
    return 0


def _head_before(structure: str, brace: int) -> str:
    start = _head_start(structure, brace)
    return structure[start:brace] if start is not None else ""


def _drop_template_prefix(head: str) -> str:
    head = head.strip()
    while _TEMPLATE_PREFIX.match(head):
        close_at = _close(head, head.index("<"))
        if close_at < 0:
            return head
        head = head[close_at + 1:].strip()
    return head


def _functions(structure: str) -> Iterator[_Function]:
    """Every function definition, from its signature (initialiser list
    included) to its closing brace. Namespaces and class bodies are walked
    into; function bodies are not."""
    stack: list[tuple[str, str | None]] = []
    pending: list[tuple[str, str | None, str, int]] = []
    for brace in re.finditer(r"[{}]", structure):
        index = brace.start()
        if brace.group() == "{":
            if any(kind not in ("namespace", "class") for kind, _name in stack):
                stack.append(("block", None))
                continue
            start = _head_start(structure, index)
            head = structure[start:index] if start is not None else ""
            kind, name = _classify(head) if start is not None else ("block", None)
            if kind == "function":
                pending.append((name, _owner_of(name, stack), _params_of(head, name), index - len(head)))
            stack.append((kind, name))
        elif stack:
            kind, _name = stack.pop()
            if kind == "function":
                name, owner, params, start = pending.pop()
                yield _Function(name=name, owner=owner, params=params, start=start, end=index)


def _classify(head: str) -> tuple[str, str | None]:
    head = _drop_template_prefix(head)
    if re.search(r"\bnamespace\b", head) or re.search(r'\bextern\s+"', head):
        return "namespace", None
    if re.search(r"\benum\b", head):
        return "other", None
    match = _CLASS_HEAD.search(head)
    if match is not None and "(" not in head[:match.start()]:
        return "class", match.group("name")
    if head.rstrip().endswith("=") or "(" not in head:
        return "other", None
    name = _function_name(head)
    return ("function", name) if name else ("other", None)


def _paren_groups(head: str) -> Iterator[tuple[int, int]]:
    index = 0
    while index < len(head):
        if head[index] == "(":
            close_at = _close(head, index)
            if close_at < 0:
                return
            yield index, close_at
            index = close_at
        index += 1


_NAME_BEFORE_PAREN = re.compile(
    r"((?:[A-Za-z_]\w*(?:\s*<[^()]*?>)?\s*::\s*)*~?[A-Za-z_]\w*|operator\s*\S+)\s*$"
)


def _function_name(head: str) -> str | None:
    """The qualified name before a parenthesised group (the first qualified
    one, else the first); ``None`` for a control statement."""
    names = []
    for open_at, _close_at in _paren_groups(head):
        match = _NAME_BEFORE_PAREN.search(head[:open_at])
        if match:
            names.append(re.sub(r"\s+", "", match.group(1)))
    name = ([n for n in names if "::" in n] or names or [None])[0]
    return None if name is None or name in _NOT_A_CALL else name


def _params_of(head: str, name: str) -> str:
    for open_at, close_at in _paren_groups(head):
        if re.sub(r"\s+", "", head[:open_at]).endswith(name):
            return head[open_at + 1:close_at]
    return ""


def _owner_of(name: str, stack: list[tuple[str, str | None]]) -> str | None:
    plain = _strip_template_args(name)
    if "::" in plain:
        return plain.split("::")[-2] or None
    return next((enclosing for kind, enclosing in reversed(stack) if kind == "class"), None)


# -- receivers and scopes ----------------------------------------------------

@dataclass(frozen=True)
class _Scope:
    root: str
    path: tuple[str, ...]


#: A receiver declared with a type that is not a dictionary: its
#: ``found``/``get`` are not dictionary reads.
NOT_A_DICTIONARY = _Scope("", ())


def _child(scope: _Scope | None, segment: str) -> _Scope | None:
    return None if scope is None else _Scope(scope.root, scope.path + (segment,))


class _Environment:
    """The dictionaries one function can name, bound in source order:
    parameters, locals (``IOdictionary`` from a literal object name
    included), entries of an iterated dictionary, the class's own
    dictionary members and accessors, and ``this`` for a dictionary class."""

    def __init__(self, text: str, structure: str, function: _Function, classes: dict[str, _Class]):
        self.text, self.structure, self.function = text, structure, function
        lineage = list(_lineage(function.owner, classes))
        self.bases = frozenset(lineage[1:])
        holder = next((name for name in lineage if _DICTIONARY_BASES & set(classes.get(name, _Class()).bases)), None)
        self.this = _Scope(f"this:{holder}", ()) if holder else None
        self.members = {
            member: f"member:{name}:{member}"
            for name in reversed(lineage) for member in classes.get(name, _Class()).dictionaries
        }
        self.others = set().union(*(classes.get(name, _Class()).others for name in lineage)) - set(self.members)
        self.dimensioned = dict(pair for name in lineage for pair in classes.get(name, _Class()).dimensioned)
        self.names: dict[str, _Scope | None] = {}
        for param in _split_args(function.params):
            match = _DICT_PARAM.search(param)
            if match:
                self.names[match.group("name")] = _Scope(f"param:{function.name}:{match.group('name')}", ())
                continue
            for declared in _DECLARATION.finditer(param):
                if _declares_other(declared):
                    self.others.add(declared.group("name"))
        self.entries: dict[str, _Scope | None] = {}
        region = structure[function.start:function.end]
        events = [(m.start(), "dict", m) for m in _DICT_DECL.finditer(region)]
        events += [(m.start(), "entry", m) for m in _ENTRY_DECL.finditer(region)]
        events += [(m.start(), "forall", m) for m in _FOR_ALL.finditer(region)]
        events += [(m.start("type"), "other", m) for m in _DECLARATION.finditer(region) if _declares_other(m)]
        self.events = sorted(events, key=lambda event: event[0])
        self.bound = 0

    def bind(self, upto: int) -> None:
        while self.bound < len(self.events) and self.function.start + self.events[self.bound][0] < upto:
            _pos, kind, match = self.events[self.bound]
            self.bound += 1
            start = self.function.start + match.end()
            if kind == "other":
                self.names.pop(match.group("name"), None)
                self.others.add(match.group("name"))
                continue
            self.others.discard(match.group("name") if kind != "forall" else "")
            if kind == "forall":
                expression = self.text[self.function.start + match.start("expr"):self.function.start + match.end("expr")]
                self.entries[match.group("iter") + "()"] = _child(self.resolve(expression), ANY_SEGMENT)
                continue
            name, expression = match.group("name"), self._initialiser(start, match.group("op"))
            if kind == "entry":
                self.entries[name] = (
                    _child(self.resolve(expression), ANY_SEGMENT) if match.group("op") == ":"
                    else self.entries.get(re.sub(r"\s+", "", expression))
                )
            elif match.group("type") == "IOdictionary":
                document = re.match(r'\s*IOobject\s*\(\s*"([^"]+)"', expression)
                self.names[name] = _Scope(f"document:{document.group(1)}", ()) if document else None
            else:
                self.names[name] = self.resolve(expression)

    def _initialiser(self, start: int, op: str) -> str:
        if op in "({":
            close_at = _close(self.structure, start - 1)
            return self.text[start:close_at] if close_at > 0 else ""
        stop = ")" if op == ":" else ";"
        depth, index = 0, start
        while index < len(self.structure):
            char = self.structure[index]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif char == stop and depth == 0:
                break
            index += 1
        return self.text[start:index]

    def resolve(self, expression: str) -> _Scope | None:
        """The scope a dictionary expression names, or ``None``."""
        steps = _steps(expression)
        if not steps:
            return None
        (name, args), rest = steps[0], steps[1:]
        if args is None and name in self.others and name not in self.names:
            return NOT_A_DICTIONARY if not rest else None
        if name == "this" and args is None:
            scope = self.this
        elif args is None and name in self.names:
            scope = self.names[name]
        elif args is None and name in self.entries:
            scope = self.entries[name]
        elif args is not None and not args.strip() and f"{name}()" in self.entries:
            scope = self.entries[f"{name}()"]
        elif args is not None and name in _SUBDICT_METHODS and self.this is not None:
            scope, rest = self.this, steps
        elif name in self.members and (args is None or not args.strip()):
            scope = _Scope(self.members[name] + ("" if args is None else "()"), ())
        else:
            return None
        for step, step_args in rest:
            if scope is None:
                return None
            if step in _SUBDICT_METHODS and step_args is not None:
                arguments = _split_args(step_args)
                literal = _literal(arguments[0]) if arguments else None
                scope = _child(scope, literal if literal is not None else ANY_SEGMENT)
            elif not (step == "dict" and step_args is not None and not step_args.strip()):
                return None
        return scope


def _steps(expression: str) -> list[tuple[str, str | None]]:
    """``a.b("x").c()`` as ``[("a", None), ("b", '"x"'), ("c", "")]``;
    ``[]`` when the expression is not such a chain."""
    expression = re.sub(r"^\s*this\s*->\s*", "", expression.strip())
    expression = re.sub(r"^\(\s*\*\s*(\w+)\s*\)", r"\1", expression)
    expression = re.sub(r"^\*\s*this\b", "this", expression)
    expression = re.sub(r"^\*\s*(?=[A-Za-z_])", "", expression)
    structure = _structure(expression)
    steps: list[tuple[str, str | None]] = []
    index = 0
    while True:
        match = _IDENT.match(structure, index)
        if match is None:
            return []
        name, index = match.group(), match.end()
        while index < len(structure) and structure[index].isspace():
            index += 1
        if structure.startswith("<", index):
            close_at = _close(structure, index)
            if close_at < 0:
                return []
            index = close_at + 1
        args = None
        if structure.startswith("(", index):
            close_at = _close(structure, index)
            if close_at < 0:
                return []
            args, index = expression[index + 1:close_at], close_at + 1
        steps.append((name, args))
        rest = structure[index:].lstrip()
        if not rest:
            return steps
        if rest.startswith("->"):
            index = len(structure) - len(rest) + 2
        elif rest.startswith("."):
            index = len(structure) - len(rest) + 1
        else:
            return []
        while index < len(structure) and structure[index].isspace():
            index += 1


def _receiver_start(structure: str, end: int, floor: int) -> int:
    """Where the receiver expression ending at ``end`` (before ``.``/``->``)
    starts: walked back over names, calls, subscripts and member access."""
    index = end
    while True:
        while index > floor and structure[index - 1].isspace():
            index -= 1
        if index > floor and structure[index - 1] in ")]":
            back = _open_before(structure, index - 1, floor)
            if back < 0:
                return index
            index = back
            name = re.search(r"[A-Za-z_]\w*\s*$", structure[floor:index])
            if name is None:
                return index
            index = floor + name.start()
        else:
            name = re.search(r"[A-Za-z_]\w*$", structure[floor:index])
            if name is None:
                return index
            index = floor + name.start()
        probe = index
        while probe > floor and structure[probe - 1].isspace():
            probe -= 1
        if structure[max(floor, probe - 2):probe] == "->":
            index = probe - 2
        elif probe > floor and structure[probe - 1] == "." :
            index = probe - 1
        else:
            return index


def _open_before(structure: str, close_at: int, floor: int) -> int:
    depth = 0
    for index in range(close_at, floor - 1, -1):
        if structure[index] in ")]":
            depth += 1
        elif structure[index] in "([":
            depth -= 1
            if depth == 0:
                return index
    return -1


# -- reads -------------------------------------------------------------------

def _reads_in(
    text: str, structure: str, function: _Function, relative: str,
    classes: dict[str, _Class], selected: dict[str, list[tuple[str, str]]],
    calls: list[tuple[str, int, int, str, tuple[str, ...]]],
) -> Iterator[DictRead]:
    region = structure[function.start:function.end]
    environment = _Environment(text, structure, function, classes)
    candidates = [(m.start(), m, "member") for m in _METHOD_CALL.finditer(region)]
    candidates += [(m.start(), m, "bare") for m in _BARE_CALL.finditer(region)]
    candidates += [(m.start(), m, "dimensioned") for m in _DIMENSIONED.finditer(region)]
    candidates += [
        (m.start(), m, "dimensioned") for m in _MEMBER_INIT.finditer(region)
        if m.group("member") in environment.dimensioned
    ]
    candidates += [(m.start(), m, "call") for m in _CALL.finditer(region)]
    selected_as = tuple(selected.get(function.owner or "", ()))
    for offset, match, kind in sorted(candidates, key=lambda item: item[0]):
        position = function.start + offset
        environment.bind(position)
        open_at = function.start + match.end() - 1
        close_at = _close(structure, open_at)
        if close_at < 0:
            continue
        args = _split_args(text[open_at + 1:close_at])
        if kind == "call":
            _record_call(re.sub(r"\s+", "", match.group("callee")), args, environment, calls)
            continue
        key = _literal(args[0]) if args else None
        if kind == "dimensioned":
            scope = environment.resolve(args[-1]) if len(args) >= 2 else None
            if scope is NOT_A_DICTIONARY or (scope is None and _NUMBER.fullmatch(args[-1] if args else "")):
                continue
            member = match.groupdict().get("member")
            method, default = "dimensioned", None
            value_type = environment.dimensioned[member] if member else re.sub(r"\s+", "", match.group("type"))
        else:
            method = match.group("method")
            if kind == "member":
                start = _receiver_start(structure, position, function.start)
                scope = environment.resolve(text[start:position]) if start < position else None
                if scope is None or scope is NOT_A_DICTIONARY:
                    enum_scope = environment.resolve(args[1]) if len(args) >= 2 and method in _ENUM_METHODS else None
                    if enum_scope is not None and enum_scope is not NOT_A_DICTIONARY:
                        scope, value_type = enum_scope, "word"
                        default = args[2] if method.endswith("OrDefault") and len(args) > 2 else None
                        yield _read(key, method, value_type, default, scope, text, position, function, relative, selected_as)
                        continue
                if scope is NOT_A_DICTIONARY:
                    continue
            elif environment.this is not None:
                start, scope = position, environment.this
            else:
                continue
            value_type = match.group("targs")[1:-1].strip() if match.group("targs") else None
            default = args[1] if len(args) > 1 and method.endswith(("OrDefault", "OrAdd")) else None
            if method == "lookup" and value_type is None:
                value_type = _wrapping_type(structure, start, function.start)
        yield _read(key, method, value_type, default, scope, text, position, function, relative, selected_as)


def _read(key, method, value_type, default, scope, text, position, function, relative, selected_as) -> DictRead:
    return DictRead(
        key=key, method=method, type=value_type, default=default,
        scope=scope.path if scope is not None else None, root=scope.root if scope is not None else None,
        file=relative, line=_line(text, position), function=function.name, selected_as=selected_as,
    )


def _record_call(callee: str, args: list[str], environment: "_Environment", calls: list) -> None:
    """A call passing a resolved dictionary: ``callee`` receives it as
    argument ``index``. A dictionary member initialised from it is recorded
    as ``=<member root>``, and a base-class constructor as ``^<class>``:
    both hold the same dictionary as the caller."""
    if callee in _KEY_METHODS | _SUBDICT_METHODS | _NOT_A_CALL | _KEYWORDS:
        return
    if callee in environment.members:
        callee = f"={environment.members[callee]}"
    elif callee.split("::")[-1] in environment.bases:
        callee = f"^{callee.split('::')[-1]}"
    for index, argument in enumerate(args):
        scope = environment.resolve(argument)
        if scope is not None and scope is not NOT_A_DICTIONARY:
            calls.append((callee, index, len(args), scope.root, scope.path))


def _wrapping_type(structure: str, start: int, floor: int) -> str | None:
    """The type a ``lookup`` result is read as: ``readScalar(d.lookup(..))``,
    ``word(d.lookup(..))``, ``const word name(d.lookup(..))``."""
    head = structure[floor:start].rstrip()
    if not head.endswith("("):
        return None
    wrapper = re.search(r"\b(" + "|".join(_WRAPPERS) + r")\s*\($", head)
    if wrapper:
        return _WRAPPERS[wrapper.group(1)]
    cast = _FUNCTIONAL_CAST.search(head)
    if cast:
        return cast.group("type")
    declared = _DECLARED_WRAPPER.search(head)
    if declared and declared.group("type") not in {"const", "return", "new", "else"}:
        return declared.group("type").replace("Foam::", "")
    return None


# -- the catalogue against the scan -----------------------------------------

#: Which catalogue ``value_kind`` each C++ type a read names can hold. A
#: catalogue may be narrower than the C++ (``integer`` for a ``scalar``
#: read); it contradicts the C++ only when its kind is outside this set.
_KINDS_BY_TYPE: dict[str, frozenset[str]] = {
    "scalar": frozenset({"scalar", "integer"}),
    "label": frozenset({"integer"}),
    "bool": frozenset({"boolean"}),
    "Switch": frozenset({"boolean"}),
    "word": frozenset({"word", "enum"}),
    "fileName": frozenset({"word", "string"}),
    "string": frozenset({"string", "word"}),
    "vector": frozenset({"vector3"}),
    "point": frozenset({"vector3"}),
    "wordList": frozenset({"word_list"}),
    "List<word>": frozenset({"word_list"}),
    "wordRes": frozenset({"word_list"}),
    "scalarList": frozenset({"scalar_list", "integer_list"}),
    "List<scalar>": frozenset({"scalar_list", "integer_list"}),
    "scalarField": frozenset({"scalar_list", "integer_list"}),
    "labelList": frozenset({"integer_list"}),
    "List<label>": frozenset({"integer_list"}),
    "vectorField": frozenset({"vector3_list"}),
    "pointField": frozenset({"vector3_list"}),
    "List<vector>": frozenset({"vector3_list"}),
    "List<point>": frozenset({"vector3_list"}),
    "dimensionedScalar": frozenset({"dimensioned_scalar", "scalar"}),
    "dimensioned<scalar>": frozenset({"dimensioned_scalar", "scalar"}),
    "dimensionedTensor": frozenset({"dimensioned_tensor"}),
}


def value_kind_of(cxx_type: str | None) -> str | None:
    """The catalogue ``value_kind`` a value of C++ type ``cxx_type`` is
    written as, or ``None`` when the type maps to no single kind."""
    kinds = _KINDS_BY_TYPE.get(re.sub(r"\s+", "", cxx_type or "").replace("Foam::", ""))
    if not kinds:
        return None
    for preferred in ("scalar", "integer", "boolean", "word", "vector3", "dimensioned_scalar"):
        if preferred in kinds:
            return preferred
    return sorted(kinds)[0]


_PLACEHOLDER = re.compile(r"<[^>]+>|\[Int\]")


def _segment_matches(read: str, listed: str) -> bool:
    return read == listed or read == ANY_SEGMENT or listed == ANY_SEGMENT or bool(_PLACEHOLDER.fullmatch(listed))


def _path_matches(read_path: tuple[str, ...], catalogue: tuple[str, ...]) -> bool:
    """Whether a read and a catalogue path can name the same key: aligned
    from the leaf, every segment both name agrees (``*`` and ``<name>`` match
    any) and at least one agrees literally. Neither side's root is known, so
    only the overlap is compared."""
    pairs = list(zip(reversed(read_path), reversed(catalogue)))
    return any(read == listed for read, listed in pairs) and all(_segment_matches(*pair) for pair in pairs)


def _anchored(read: DictRead, catalogue: tuple[str, ...], entry) -> bool:
    """Whether a matching read is evidence about this entry rather than a
    same-named key elsewhere: it agrees beyond the final name, or it is read
    in a file the entry cites."""
    pairs = list(zip(reversed(read.scope + (read.key,)), reversed(catalogue)))[1:]
    return any(r == listed and not _PLACEHOLDER.fullmatch(listed) for r, listed in pairs) or any(
        ref == read.file or ref.endswith("/" + read.file) for ref in entry.source_refs
    )


def locate(scan: Scan, entries: Iterable, *, document: str) -> dict[str, frozenset[tuple[str, ...]]]:
    """Where each root sits in ``document``, whose keys ``entries``
    catalogue, as catalogue path prefixes (``$TOKEN`` and ``<name>``
    segments kept).

    A root is placed by the catalogued keys read on it, each named literally
    by the catalogue and anchored to the entry (``_anchored``): every one of
    its reads must fit, so its place is the intersection of the places each
    read allows. A root with no such read takes its place from the
    dictionaries the calls in the scan pass to it; a parameter that
    initialises a placed member, or is passed to a placed base-class
    constructor, and ``document`` itself when passed to a placed parameter,
    take theirs. Another document's root, and a root placed
    by none of these, stay unplaced."""
    entries = tuple(entries)
    paths = [(entry, tuple(entry.driver_path.split("."))) for entry in entries]
    foreign = {read.root for read in scan.reads if read.root and read.root.startswith("document:")} - {f"document:{document}"}
    allowed: dict[str, list[set[tuple[str, ...]]]] = {}
    for read in scan.reads:
        if read.key is None or read.scope is None or read.root in foreign or read.method in _PROBES - {"findDict"}:
            continue
        route = read.scope + (read.key,)
        places = {
            path[:start]
            for entry, path in paths for start in range(len(path) - len(route) + 1)
            if (start + len(route) < len(path) if read.subdict else start + len(route) == len(path))
            and path[start + len(route) - 1] == read.key
            and all(_segment_matches(*pair) for pair in zip(route, path[start:]))
            and _anchored(read, path[:start + len(route)], entry)
        }
        if places:
            allowed.setdefault(read.root, []).append(places)
    placed = {root: frozenset(set.intersection(*sets)) for root, sets in allowed.items()}
    placed = {root: places for root, places in placed.items() if places}
    edges = []
    for callee, index, count, root, scope in scan.calls:
        if callee.startswith("="):
            edges.append((root, scope, callee[1:], True))
            continue
        same = callee.startswith("^")
        name = f"{callee[1:]}::{callee[1:]}" if same else callee
        edges += [
            (root, scope, parameter, same) for function, position, total, parameter in scan.parameters
            if position == index and count <= total and _same_function(function, name)
        ]
    edges = [edge for edge in edges if not {edge[0], edge[2]} & foreign]
    while True:
        found: dict[str, set[tuple[str, ...]]] = {}
        for source, scope, target, same in edges:
            if target not in placed and source in placed:
                found.setdefault(target, set()).update(place + scope for place in placed[source])
            elif (same or source == f"document:{document}") and source not in placed and target in placed:
                found.setdefault(source, set()).update(
                    place[:len(place) - len(scope)] for place in placed[target]
                    if len(place) >= len(scope) and all(_segment_matches(*pair) for pair in zip(scope, place[len(place) - len(scope):]))
                )
        found = {root: places for root, places in found.items() if places}
        if not found:
            return placed
        placed.update({root: frozenset(places) for root, places in found.items()})


def _same_function(defined: str, called: str) -> bool:
    """A definition and a call name one function when one spelling is the
    other with more of its namespace or class qualification."""
    return defined == called or defined.endswith("::" + called) or called.endswith("::" + defined)


@dataclass(frozen=True)
class CatalogReport:
    """The catalogue compared with the scan. ``contradictions`` are catalogue
    claims the C++ refutes, each naming both sides; ``uncatalogued`` are
    what the C++ reads and the catalogue lacks; ``unresolved`` are reads the
    scan could not place (their receiver is not shown to be a dictionary)."""

    status: str
    digest: str
    resolution: dict[str, object]
    contradictions: list[str]
    uncatalogued: list[dict]
    unresolved: list[dict]
    selector_values: dict[str, list[str]]

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def catalog_report(
    source_root: Path, *, allowlist_path: Path, entries: Iterable,
    cache_root: Path | None = None, force: bool = False,
) -> CatalogReport:
    """Compare the catalogue ``entries`` with the scan of ``source_root``.

    ``allowlist_path`` is the plugin's reviewed file: ``unseen_reads``
    (why -> catalogued paths whose read the scan cannot see: read outside
    this source, or by a non-literal key) and ``runtime_selection`` (which
    selection table each enum draws its menu from). A read counts against an
    entry's type or required flag only when it is anchored to it
    (``_anchored``), so a same-named key elsewhere never fails a plan."""
    from .rtst_scanner import runtime_selection_report

    scan = cached_scan(source_root, cache_root=cache_root, force=force)
    reviewed = json.loads(Path(allowlist_path).read_text())
    unseen = {path: why for why, paths in reviewed.get("unseen_reads", {}).items() for path in paths}
    entries = tuple(entries)
    catalogue = [(entry, tuple(path.split("."))) for entry, path in zip(entries, catalogued_paths(entries))]
    containers = [path[:i] for _entry, path in catalogue for i in range(1, len(path))]

    contradictions: list[str] = []
    read_keys = {read.key for read in scan.reads if read.key is not None}
    for entry, path in catalogue:
        if _PLACEHOLDER.fullmatch(path[-1]) or entry.driver_path in unseen:
            continue
        if path[-1] not in read_keys:
            contradictions.append(f"{entry.driver_path}: catalogued, but the C++ reads no {path[-1]!r}")
            continue
        reads = [
            read for read in scan.reads
            if read.value_read and read.key == path[-1]
            and _path_matches(read.scope + (read.key,), path) and _anchored(read, path, entry)
        ]
        typed = [read for read in reads if read.type in _KINDS_BY_TYPE]
        if typed and not any(entry.value_kind in _KINDS_BY_TYPE[read.type] for read in typed):
            contradictions.append(
                f"{entry.driver_path}: catalogue value_kind {entry.value_kind!r}; the C++ reads "
                + ", ".join(sorted({f"{read.type} ({read.file}:{read.line})" for read in typed}))
            )
        if entry.required and reads and all(read.default is not None for read in reads):
            contradictions.append(
                f"{entry.driver_path}: catalogue says required; the C++ gives it a default ("
                + ", ".join(sorted({f"{read.default} at {read.file}:{read.line}" for read in reads})) + ")"
            )
    contradictions += [
        f"unseen_reads names {path}, which the catalogue does not list"
        for path in sorted(set(unseen) - {entry.driver_path for entry in entries})
    ]

    uncatalogued: list[dict] = []
    seen: set[tuple] = set()
    for read in scan.reads:
        if read.key is None or read.scope is None or read.method in _PROBES:
            continue
        read_path = read.scope + (read.key,)
        listed = [path for _entry, path in catalogue] + (containers if read.subdict else [])
        if any(_path_matches(read_path, path) for path in listed) or (read.root, read_path, read.method) in seen:
            continue
        seen.add((read.root, read_path, read.method))
        uncatalogued.append({
            "kind": "dictionary" if read.subdict else "key",
            "key": read.key, "path": ".".join(read_path), "root": read.root,
            "type": read.type, "value_kind": value_kind_of(read.type), "default": read.default,
            "method": read.method, "source": f"{read.file}:{read.line}", "function": read.function,
            "selected_as": [list(pair) for pair in read.selected_as],
        })

    selection = runtime_selection_report(
        scan.registrations, entries=entries, mapping=reviewed.get("runtime_selection", {}),
    ) if "runtime_selection" in reviewed else {"contradictions": [], "uncatalogued": [], "selector_values": {}}
    contradictions += selection["contradictions"]
    return CatalogReport(
        status="failed" if contradictions else "ok",
        digest=scan.digest,
        resolution=scan.resolution(),
        contradictions=contradictions,
        uncatalogued=uncatalogued + selection["uncatalogued"],
        unresolved=[
            {"key": read.key, "method": read.method, "source": f"{read.file}:{read.line}", "function": read.function}
            for read in scan.reads if read.scope is None and read.key is not None and read.method not in _PROBES
        ],
        selector_values=selection["selector_values"],
    )


def registered_menu(mapping, driver_path: str) -> frozenset[str]:
    """The names the scanned selection table behind the enum at
    ``driver_path`` registers, when the plugin's source is supplied and its
    reviewed ``runtime_selection`` maps the enum to a table (not as a
    curated ``subset``); empty otherwise. A menu check accepts these and the
    plan reports the ones the catalogue lacks as uncatalogued."""
    root = mapping.source_root(os.environ) if mapping is not None else None
    if root is None or not root.is_dir():
        return frozenset()
    rule = json.loads(mapping.allowlist_path.read_text()).get("runtime_selection", {}).get("by_path", {}).get(driver_path)
    if rule is None or rule.get("mode") == "subset":
        return frozenset()
    return frozenset(cached_scan(root, cache_root=None).registrations.get(rule["base"], {}))
