#!/usr/bin/env python3

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


FENCE_JSON_PATTERN = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.MULTILINE)
PAGE_LINK_PATTERN = re.compile(r"^\s*Page Link:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
QUERY_PATTERN = re.compile(r"^\s*Query:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


@dataclass
class SourceSummary:
	source_dir: str
	files_scanned: int
	items_extracted: int


@dataclass
class JobItem:
	job_title: Optional[str]
	url: Optional[str]
	location: Optional[str] = None
	company_url: Optional[str] = None


@dataclass
class ExtractedEntry:
	page_link: Optional[str]
	query: Optional[str]
	source_file: str
	status: Optional[str]
	has_jobs: bool
	jobs: List[JobItem]
	jobs_from_snippet: List[JobItem]
	content: Dict[str, Any]


def read_text(path: Path) -> str:
	return path.read_text(encoding="utf-8", errors="replace")


def parse_markdown_block(md_text: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
	"""Extract page link, query, and the JSON object from an extracted_content_*.md file."""
	page_link_match = PAGE_LINK_PATTERN.search(md_text)
	query_match = QUERY_PATTERN.search(md_text)
	json_match = FENCE_JSON_PATTERN.search(md_text)

	page_link = page_link_match.group(1).strip() if page_link_match else None
	query = query_match.group(1).strip() if query_match else None

	parsed_json: Optional[Dict[str, Any]] = None
	if json_match:
		json_str = json_match.group(1)
		try:
			parsed_json = json.loads(json_str)
		except json.JSONDecodeError as e:
			# Try a minimal cleanup fallback if trailing commas exist (best-effort)
			json_str_min = re.sub(r",(\s*[}\]])", r"\1", json_str)
			try:
				parsed_json = json.loads(json_str_min)
			except Exception:
				parsed_json = None

	return page_link, query, parsed_json


def extract_jobs_from_content(content: Dict[str, Any]) -> Tuple[List[JobItem], List[JobItem]]:
	"""Return (jobs, jobs_from_snippet) based on content shape."""
	jobs: List[JobItem] = []
	jobs_from_snippet: List[JobItem] = []

	# Primary: explicit jobs array
	if isinstance(content.get("jobs"), list):
		for j in content["jobs"]:
			if isinstance(j, dict):
				jobs.append(
					JobItem(
						job_title=j.get("job_title") if isinstance(j.get("job_title"), str) else None,
						url=j.get("url") or j.get("link"),
						location=j.get("location") if isinstance(j.get("location"), str) else None,
						company_url=j.get("company_url") if isinstance(j.get("company_url"), str) else None,
					)
				)

	# Secondary: parse markdown links from a relevant snippet (best-effort)
	relevant_snippet = content.get("relevant_snippet")
	if isinstance(relevant_snippet, str) and relevant_snippet.strip():
		for title, url in MARKDOWN_LINK_PATTERN.findall(relevant_snippet):
			jobs_from_snippet.append(JobItem(job_title=title.strip(), url=url.strip()))

	return jobs, jobs_from_snippet


def should_include_entry(status: Optional[str], jobs: List[JobItem], jobs_from_snippet: List[JobItem]) -> bool:
	# Include if status is explicitly success OR there are explicit jobs OR jobs inferred from snippet
	if status and status.strip().lower() == "success":
		return True
	if jobs:
		return True
	if jobs_from_snippet:
		return True
	return False


def scan_directories(input_dirs: List[Path]) -> Tuple[List[ExtractedEntry], List[SourceSummary]]:
	results: List[ExtractedEntry] = []
	summaries: List[SourceSummary] = []

	for in_dir in input_dirs:
		files = list(in_dir.rglob("extracted_content_*.md"))
		items_extracted = 0
		for f in files:
			try:
				md_text = read_text(f)
				page_link, query, content = parse_markdown_block(md_text)
				if not content:
					continue
				status = None
				if isinstance(content.get("status"), str):
					status = content["status"]

				jobs, jobs_from_snippet = extract_jobs_from_content(content)
				has_jobs = bool(jobs or jobs_from_snippet)

				if should_include_entry(status, jobs, jobs_from_snippet):
					entry = ExtractedEntry(
						page_link=page_link,
						query=query,
						source_file=str(f.resolve()),
						status=status,
						has_jobs=has_jobs,
						jobs=jobs,
						jobs_from_snippet=jobs_from_snippet,
						content=content,
					)
					results.append(entry)
					items_extracted += 1
			except Exception as e:
				# Continue scanning on individual file failures
				continue

		summaries.append(
			SourceSummary(
				source_dir=str(in_dir.resolve()),
				files_scanned=len(files),
				items_extracted=items_extracted,
			)
		)

	return results, summaries


def build_output_payload(results: List[ExtractedEntry], summaries: List[SourceSummary]) -> Dict[str, Any]:
	return {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"results_count": len(results),
		"sources": [asdict(s) for s in summaries],
		"results": [
			{
				"page_link": r.page_link,
				"query": r.query,
				"source_file": r.source_file,
				"status": r.status,
				"has_jobs": r.has_jobs,
				"jobs": [asdict(j) for j in r.jobs],
				"jobs_from_snippet": [asdict(j) for j in r.jobs_from_snippet],
				"content": r.content,
			}
			for r in results
		],
	}


def main(argv: Optional[List[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Aggregate job listings from extracted_content_*.md files.")
	parser.add_argument(
		"inputs",
		nargs="+",
		help="One or more directories to scan (recursively)",
	)
	parser.add_argument(
		"-o",
		"--output",
		type=str,
		default="-",
		help="Output file path, or '-' for stdout (default)",
	)
	args = parser.parse_args(argv)

	input_dirs: List[Path] = []
	for p in args.inputs:
		path = Path(p).expanduser()
		if not path.exists() or not path.is_dir():
			print(f"Skipping non-directory input: {p}", file=sys.stderr)
			continue
		input_dirs.append(path)

	if not input_dirs:
		print("No valid input directories provided.", file=sys.stderr)
		return 2

	results, summaries = scan_directories(input_dirs)
	payload = build_output_payload(results, summaries)
	output_str = json.dumps(payload, indent=2, ensure_ascii=False)

	if args.output == "-":
		print(output_str)
	else:
		out_path = Path(args.output).expanduser()
		out_path.parent.mkdir(parents=True, exist_ok=True)
		out_path.write_text(output_str, encoding="utf-8")
		print(f"Wrote {len(results)} results to {str(out_path.resolve())}")

	return 0


if __name__ == "__main__":
	sys.exit(main()) 