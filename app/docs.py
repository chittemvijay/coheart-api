from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import shutil

BASE = Path(__file__).parent.parent / 'data' / 'docs'
BASE.mkdir(parents=True, exist_ok=True)

# documents: id -> {id, title, versions: [ {version, filename, stored_path, uploaded_by, timestamp, size} ] }
documents: Dict[str, Dict] = {}


def _next_version(doc_id: str) -> int:
    doc = documents.get(doc_id)
    if not doc:
        return 1
    return (doc.get('versions') and max(v.get('version', 0) for v in doc.get('versions', [])) or 0) + 1


def save_file_bytes(doc_id: str, original_filename: str, data: bytes, uploaded_by: str) -> Dict:
    version = _next_version(doc_id)
    doc_dir = BASE / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"v{version}_{original_filename}"
    stored_path = doc_dir / stored_name
    with open(stored_path, 'wb') as f:
        f.write(data)
    entry = {
        'version': version,
        'filename': original_filename,
        'stored_path': str(stored_path),
        'uploaded_by': uploaded_by,
        'timestamp': datetime.utcnow().isoformat(),
        'size': len(data),
    }
    documents.setdefault(doc_id, {'id': doc_id, 'title': doc_id, 'versions': []})
    documents[doc_id]['versions'].append(entry)
    return entry


def create_document(doc_id: str, title: str, original_filename: str, data: bytes, uploaded_by: str) -> Dict:
    if doc_id in documents:
        raise ValueError('document exists')
    documents[doc_id] = {'id': doc_id, 'title': title, 'versions': []}
    entry = save_file_bytes(doc_id, original_filename, data, uploaded_by)
    documents[doc_id]['title'] = title
    return documents[doc_id]


def add_version(doc_id: str, original_filename: str, data: bytes, uploaded_by: str) -> Dict:
    if doc_id not in documents:
        raise KeyError('not found')
    return save_file_bytes(doc_id, original_filename, data, uploaded_by)


def list_documents() -> List[Dict]:
    return list(documents.values())


def list_versions(doc_id: str) -> List[Dict]:
    doc = documents.get(doc_id)
    if not doc:
        raise KeyError('not found')
    return doc.get('versions', [])


def get_version_file_path(doc_id: str, version: int) -> Optional[str]:
    vers = list_versions(doc_id)
    for v in vers:
        if v.get('version') == version:
            return v.get('stored_path')
    return None


def delete_document(doc_id: str) -> None:
    doc_dir = BASE / doc_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)
    documents.pop(doc_id, None)
