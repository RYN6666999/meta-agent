from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from shutil import which
import json
import os
import shlex
import subprocess
from typing import Any


@dataclass
class CodeIntelRequest:
    kind: str
    target: str = ''
    query: str = ''
    repo: str = 'meta-agent'
    max_depth: int = 3
    include_tests: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeIntelSummary:
    overview: str
    top_symbols: list[str] = field(default_factory=list)
    affected_paths: list[str] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    risk_level: str = 'unknown'
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeIntelResult:
    ok: bool
    provider: str
    mode: str
    request_kind: str
    checked_at: str
    available: bool
    summary: CodeIntelSummary | None = None
    error: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodeIntelligenceAdapter:
    def is_available(self) -> bool:
        raise NotImplementedError

    def overview(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def symbol_context(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def impact(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError

    def process_search(self, request: CodeIntelRequest) -> CodeIntelResult:
        raise NotImplementedError


class NullCodeIntelligenceAdapter(CodeIntelligenceAdapter):
    def _result(self, request: CodeIntelRequest, error: str) -> CodeIntelResult:
        return CodeIntelResult(
            ok=False,
            provider='none',
            mode='disabled',
            request_kind=request.kind,
            checked_at=_now(),
            available=False,
            error=error,
        )

    def is_available(self) -> bool:
        return False

    def overview(self, request: CodeIntelRequest) -> CodeIntelResult:
        return self._result(request, 'code intelligence provider is unavailable')

    def symbol_context(self, request: CodeIntelRequest) -> CodeIntelResult:
        return self._result(request, 'code intelligence provider is unavailable')

    def impact(self, request: CodeIntelRequest) -> CodeIntelResult:
        return self._result(request, 'code intelligence provider is unavailable')

    def process_search(self, request: CodeIntelRequest) -> CodeIntelResult:
        return self._result(request, 'code intelligence provider is unavailable')


class GitNexusLocalAdapter(CodeIntelligenceAdapter):
    def __init__(
        self,
        *,
        command: str | None = None,
        working_dir: str | Path | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.command = command or os.environ.get('GITNEXUS_COMMAND', 'gitnexus')
        self.working_dir = Path(working_dir or os.environ.get('GITNEXUS_WORKDIR', '.')).resolve()
        self.timeout_seconds = timeout_seconds
        self._command_parts = shlex.split(self.command)

    def is_available(self) -> bool:
        if not self._command_parts:
            return False
        executable = self._command_parts[0]
        if Path(executable).exists():
            return True
        return which(executable) is not None

    def overview(self, request: CodeIntelRequest) -> CodeIntelResult:
        if not self.is_available():
            return _unavailable_result(request, provider='gitnexus', mode='local-cli')

        status_result = self._run(['status'])
        if not status_result['ok']:
            return _error_result(request, provider='gitnexus', mode='local-cli', error=status_result['error'])

        repo_result = self._run(['list'])
        repo_stdout = repo_result['stdout'] if repo_result['ok'] else ''
        overview = _first_non_empty_paragraph(status_result['stdout']) or 'GitNexus status available.'
        top_symbols = _extract_symbol_candidates(status_result['stdout'])[:5]
        affected_paths = _extract_paths(status_result['stdout'])[:5]
        raw = {
            'status_stdout': status_result['stdout'][:4000],
        }
        if repo_stdout:
            raw['list_stdout'] = repo_stdout[:2000]

        return CodeIntelResult(
            ok=True,
            provider='gitnexus',
            mode='local-cli',
            request_kind=request.kind,
            checked_at=_now(),
            available=True,
            summary=CodeIntelSummary(
                overview=overview,
                top_symbols=top_symbols,
                affected_paths=affected_paths,
                processes=[],
                risk_level='low',
                raw=raw,
            ),
        )

    def symbol_context(self, request: CodeIntelRequest) -> CodeIntelResult:
        if not self.is_available():
            return _unavailable_result(request, provider='gitnexus', mode='local-cli')
        if not request.target.strip():
            return _error_result(request, provider='gitnexus', mode='local-cli', error='symbol_context requires target')

        args = ['context', request.target]
        if request.repo:
            args.extend(['--repo', request.repo])
        result = self._run(args)
        if not result['ok']:
            return _error_result(request, provider='gitnexus', mode='local-cli', error=result['error'])

        output = result['stdout']
        parsed = _parse_json_output(output)
        return CodeIntelResult(
            ok=True,
            provider='gitnexus',
            mode='local-cli',
            request_kind=request.kind,
            checked_at=_now(),
            available=True,
            summary=CodeIntelSummary(
                overview=_summarize_context(parsed, output, request.target),
                top_symbols=_extract_symbols_from_any(parsed, output)[:8],
                affected_paths=_extract_paths_from_any(parsed, output)[:8],
                processes=_extract_processes_from_any(parsed, output)[:5],
                risk_level=_extract_risk_from_any(parsed, output, default='medium'),
                raw=_build_raw_payload(parsed, output),
            ),
        )

    def impact(self, request: CodeIntelRequest) -> CodeIntelResult:
        if not self.is_available():
            return _unavailable_result(request, provider='gitnexus', mode='local-cli')
        if not request.target.strip():
            return _error_result(request, provider='gitnexus', mode='local-cli', error='impact requires target')

        direction = str(request.metadata.get('direction') or 'upstream')
        args = ['impact', request.target, '--direction', direction, '--depth', str(max(1, request.max_depth))]
        if request.repo:
            args.extend(['--repo', request.repo])
        if request.include_tests:
            args.append('--include-tests')

        result = self._run(args)
        if not result['ok']:
            return _error_result(request, provider='gitnexus', mode='local-cli', error=result['error'])

        output = result['stdout']
        parsed = _parse_json_output(output)
        risk_level = _extract_risk_from_any(parsed, output)
        return CodeIntelResult(
            ok=True,
            provider='gitnexus',
            mode='local-cli',
            request_kind=request.kind,
            checked_at=_now(),
            available=True,
            summary=CodeIntelSummary(
                overview=_summarize_impact(parsed, output, request.target),
                top_symbols=_extract_symbols_from_any(parsed, output)[:8],
                affected_paths=_extract_paths_from_any(parsed, output)[:8],
                processes=_extract_processes_from_any(parsed, output)[:5],
                risk_level=risk_level,
                raw={**_build_raw_payload(parsed, output), 'direction': direction},
            ),
        )

    def process_search(self, request: CodeIntelRequest) -> CodeIntelResult:
        if not self.is_available():
            return _unavailable_result(request, provider='gitnexus', mode='local-cli')
        if not request.query.strip():
            return _error_result(request, provider='gitnexus', mode='local-cli', error='process_search requires query')

        args = ['query', request.query]
        if request.repo:
            args.extend(['--repo', request.repo])
        goal = str(request.metadata.get('goal') or '').strip()
        task_context = str(request.metadata.get('context') or '').strip()
        if goal:
            args.extend(['--goal', goal])
        if task_context:
            args.extend(['--context', task_context])

        result = self._run(args)
        if not result['ok']:
            return _error_result(request, provider='gitnexus', mode='local-cli', error=result['error'])

        output = result['stdout']
        parsed = _parse_json_output(output)
        return CodeIntelResult(
            ok=True,
            provider='gitnexus',
            mode='local-cli',
            request_kind=request.kind,
            checked_at=_now(),
            available=True,
            summary=CodeIntelSummary(
                overview=_summarize_query(parsed, output, request.query),
                top_symbols=_extract_symbols_from_any(parsed, output)[:8],
                affected_paths=_extract_paths_from_any(parsed, output)[:8],
                processes=_extract_processes_from_any(parsed, output)[:5],
                risk_level=_extract_risk_from_any(parsed, output, default='medium'),
                raw=_build_raw_payload(parsed, output),
            ),
        )

    def _run(self, args: list[str]) -> dict[str, Any]:
        command = [*self._command_parts, *args]
        try:
            result = subprocess.run(
                command,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return {'ok': False, 'stdout': '', 'error': f'command not found: {self.command}'}
        except subprocess.TimeoutExpired:
            return {'ok': False, 'stdout': '', 'error': f'command timed out after {self.timeout_seconds}s'}
        except Exception as exc:
            return {'ok': False, 'stdout': '', 'error': str(exc)}

        stdout = _normalize_output(result.stdout, result.stderr)
        if result.returncode != 0:
            error = stdout or f'command failed with exit code {result.returncode}'
            return {'ok': False, 'stdout': stdout, 'error': error[:500]}
        return {'ok': True, 'stdout': stdout, 'error': ''}


def get_code_intelligence_adapter(
    *,
    provider: str | None = None,
    working_dir: str | Path | None = None,
) -> CodeIntelligenceAdapter:
    selected = (provider or os.environ.get('CODE_INTELLIGENCE_PROVIDER') or 'gitnexus').strip().lower()
    if selected in {'none', 'disabled', 'off'}:
        return NullCodeIntelligenceAdapter()

    if selected == 'gitnexus':
        adapter = GitNexusLocalAdapter(working_dir=working_dir)
        return adapter if adapter.is_available() else NullCodeIntelligenceAdapter()

    return NullCodeIntelligenceAdapter()


def serialize_code_intel_result(result: CodeIntelResult) -> dict[str, Any]:
    return result.to_dict()


def build_failure_enrichment(
    detail: str,
    *,
    repo: str = 'meta-agent',
    target: str = '',
    working_dir: str | Path | None = None,
) -> CodeIntelResult:
    adapter = get_code_intelligence_adapter(working_dir=working_dir)
    request = CodeIntelRequest(
        kind='failure_enrichment',
        target=target,
        query=detail,
        repo=repo,
        metadata={
            'context': 'validation failure diagnosis',
            'goal': 'identify likely impacted code paths and symbols',
        },
    )

    if not adapter.is_available():
        return _unavailable_result(request, provider='gitnexus', mode='local-cli')

    overview = adapter.overview(CodeIntelRequest(kind='overview', repo=repo))
    search = adapter.process_search(
        CodeIntelRequest(
            kind='failure_enrichment',
            query=detail,
            repo=repo,
            metadata={
                'context': 'validation failure diagnosis',
                'goal': 'identify related execution flows and symbols',
            },
        )
    )

    summaries = [result.summary for result in (overview, search) if result.ok and result.summary]
    if not summaries:
        error = search.error or overview.error or 'failure enrichment unavailable'
        return _error_result(request, provider='gitnexus', mode='local-cli', error=error)

    top_symbols = _merge_unique_lists(*(summary.top_symbols for summary in summaries), limit=8)
    affected_paths = _merge_unique_lists(*(summary.affected_paths for summary in summaries), limit=8)
    processes = _merge_unique_lists(*(summary.processes for summary in summaries), limit=5)
    risk_level = _merge_risk_levels(*(summary.risk_level for summary in summaries))
    overview_text = _merge_overview_texts(*(summary.overview for summary in summaries if summary.overview))
    raw = {
        'detail': detail[:500],
        'overview': overview.to_dict(),
        'search': search.to_dict(),
    }

    return CodeIntelResult(
        ok=True,
        provider='gitnexus',
        mode='local-cli',
        request_kind=request.kind,
        checked_at=_now(),
        available=True,
        summary=CodeIntelSummary(
            overview=overview_text,
            top_symbols=top_symbols,
            affected_paths=affected_paths,
            processes=processes,
            risk_level=risk_level,
            raw=raw,
        ),
    )


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _normalize_output(stdout: str, stderr: str) -> str:
    parts = []
    if stdout and stdout.strip():
        parts.append(stdout.strip())
    if stderr and stderr.strip():
        parts.append(stderr.strip())
    return '\n'.join(parts).strip()


def _parse_json_output(text: str) -> dict[str, Any] | list[Any] | None:
    candidate = text.strip()
    if not candidate:
        return None
    if not (candidate.startswith('{') or candidate.startswith('[')):
        return None
    try:
        parsed = json.loads(candidate)
    except Exception:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _unavailable_result(request: CodeIntelRequest, *, provider: str, mode: str) -> CodeIntelResult:
    return CodeIntelResult(
        ok=False,
        provider=provider,
        mode=mode,
        request_kind=request.kind,
        checked_at=_now(),
        available=False,
        error='provider unavailable',
    )


def _error_result(request: CodeIntelRequest, *, provider: str, mode: str, error: str) -> CodeIntelResult:
    return CodeIntelResult(
        ok=False,
        provider=provider,
        mode=mode,
        request_kind=request.kind,
        checked_at=_now(),
        available=True,
        error=error,
    )


def _first_non_empty_paragraph(text: str) -> str:
    for block in text.split('\n\n'):
        cleaned = ' '.join(line.strip() for line in block.splitlines() if line.strip())
        if cleaned:
            return cleaned[:280]
    return ''


def _extract_paths(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for token in text.replace('(', ' ').replace(')', ' ').split():
        candidate = token.strip(',:;[]{}')
        if '/' not in candidate:
            continue
        if '.' not in candidate.rsplit('/', 1)[-1]:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return found


def _extract_paths_from_any(parsed: dict[str, Any] | list[Any] | None, text: str) -> list[str]:
    if parsed is None:
        return _extract_paths(text)
    found: list[str] = []
    seen: set[str] = set()
    for item in _walk_json(parsed):
        if not isinstance(item, str):
            continue
        if '/' not in item:
            continue
        if item in seen:
            continue
        seen.add(item)
        found.append(item)
    return found


def _extract_symbol_candidates(text: str) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ' -> ' in stripped:
            stripped = stripped.split(' -> ', 1)[0].strip()
        if ': ' in stripped and stripped.split(': ', 1)[0].lower() in {'target', 'symbol', 'name'}:
            stripped = stripped.split(': ', 1)[1].strip()
        candidate = stripped.split(' [', 1)[0].split(' (', 1)[0].strip('-*0123456789. ')
        if not candidate or len(candidate) > 120:
            continue
        if '/' in candidate:
            continue
        if candidate.lower() in {'upstream', 'downstream', 'processes', 'definitions', 'summary'}:
            continue
        if candidate in seen:
            continue
        if not any(ch.isalpha() for ch in candidate):
            continue
        seen.add(candidate)
        results.append(candidate)
    return results


def _extract_symbols_from_any(parsed: dict[str, Any] | list[Any] | None, text: str) -> list[str]:
    if parsed is None:
        return _extract_symbol_candidates(text)
    found: list[str] = []
    seen: set[str] = set()
    preferred_keys = {'name', 'target', 'symbol', 'id'}
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            if key in preferred_keys:
                _collect_symbol_value(value, found, seen)
        for item in _walk_json(parsed):
            _collect_symbol_value(item, found, seen)
    else:
        for item in _walk_json(parsed):
            _collect_symbol_value(item, found, seen)
    return found


def _extract_processes(text: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    capture = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith('processes'):
            capture = True
            continue
        if capture and not stripped:
            capture = False
            continue
        if capture and stripped.startswith('-'):
            candidate = stripped.lstrip('- ').split(':', 1)[0].strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                items.append(candidate)
    return items


def _extract_processes_from_any(parsed: dict[str, Any] | list[Any] | None, text: str) -> list[str]:
    if parsed is None:
        return _extract_processes(text)
    items: list[str] = []
    seen: set[str] = set()
    for value in _walk_json(parsed):
        if not isinstance(value, str):
            continue
        if '→' in value or '->' in value:
            if value not in seen:
                seen.add(value)
                items.append(value)
        elif value.lower().endswith('flow') and value not in seen:
            seen.add(value)
            items.append(value)
    return items


def _infer_risk_level(text: str) -> str:
    lowered = text.lower()
    if 'will break' in lowered or 'high risk' in lowered:
        return 'high'
    if 'likely affected' in lowered or 'medium risk' in lowered:
        return 'medium'
    if 'may need testing' in lowered or 'low risk' in lowered:
        return 'low'
    return 'unknown'


def _extract_risk_from_any(parsed: dict[str, Any] | list[Any] | None, text: str, default: str = 'unknown') -> str:
    if isinstance(parsed, dict):
        for key in ('risk', 'risk_level'):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                normalized = value.strip().lower()
                if normalized == 'critical':
                    return 'high'
                if normalized in {'high', 'medium', 'low'}:
                    return normalized
    inferred = _infer_risk_level(text)
    return inferred if inferred != 'unknown' else default


def _summarize_impact(parsed: dict[str, Any] | list[Any] | None, text: str, target: str) -> str:
    if isinstance(parsed, dict):
        target_name = target
        target_data = parsed.get('target')
        if isinstance(target_data, dict):
            target_name = str(target_data.get('name') or target_name)
        impacted = parsed.get('impactedCount')
        risk = parsed.get('risk')
        summary = parsed.get('summary')
        if isinstance(summary, dict):
            direct = summary.get('direct')
            processes = summary.get('processes_affected')
            modules = summary.get('modules_affected')
            return f'Impact for {target_name}: impacted={impacted}, direct={direct}, processes={processes}, modules={modules}, risk={risk}'.strip()
        return f'Impact for {target_name}: impacted={impacted}, risk={risk}'.strip()
    return _first_non_empty_paragraph(text) or f'Impact for {target}'


def _summarize_context(parsed: dict[str, Any] | list[Any] | None, text: str, target: str) -> str:
    if isinstance(parsed, dict):
        symbol = parsed.get('symbol')
        if isinstance(symbol, dict):
            name = symbol.get('name') or target
            file_path = symbol.get('filePath') or ''
            return f'Context for {name} in {file_path}'.strip()
    return _first_non_empty_paragraph(text) or f'Context for {target}'


def _summarize_query(parsed: dict[str, Any] | list[Any] | None, text: str, query: str) -> str:
    if isinstance(parsed, dict):
        process_count = len(parsed.get('processes', [])) if isinstance(parsed.get('processes'), list) else 0
        defs = len(parsed.get('definitions', [])) if isinstance(parsed.get('definitions'), list) else 0
        return f'Query "{query}" matched {process_count} processes and {defs} definitions.'
    return _first_non_empty_paragraph(text) or f'Process search for {query}'


def _build_raw_payload(parsed: dict[str, Any] | list[Any] | None, output: str) -> dict[str, Any]:
    if parsed is not None:
        return {'parsed': parsed}
    return {'stdout': output[:4000]}


def _walk_json(value: Any):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_json(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _walk_json(nested)
        return
    yield value


def _collect_symbol_value(value: Any, found: list[str], seen: set[str]) -> None:
    if isinstance(value, dict):
        name = value.get('name')
        if isinstance(name, str) and name and name not in seen:
            seen.add(name)
            found.append(name)
        return
    if not isinstance(value, str):
        return
    candidate = value.strip()
    if not candidate or len(candidate) > 120:
        return
    if candidate in seen:
        return
    if '/' in candidate and ':' not in candidate:
        return
    if not any(ch.isalpha() for ch in candidate):
        return
    seen.add(candidate)
    found.append(candidate)


def _merge_unique_lists(*items: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in items:
        for item in group:
            if not item or item in seen:
                continue
            seen.add(item)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _merge_risk_levels(*levels: str) -> str:
    priority = {'high': 3, 'medium': 2, 'low': 1, 'unknown': 0}
    best = 'unknown'
    score = -1
    for level in levels:
        current = priority.get(level or 'unknown', 0)
        if current > score:
            score = current
            best = level or 'unknown'
    return best


def _merge_overview_texts(*texts: str) -> str:
    cleaned = [text.strip() for text in texts if text and text.strip()]
    if not cleaned:
        return 'Failure enrichment unavailable.'
    if len(cleaned) == 1:
        return cleaned[0][:280]
    return ' | '.join(cleaned[:2])[:280]