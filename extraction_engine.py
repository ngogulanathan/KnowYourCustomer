
import zipfile
import re
from pathlib import Path
import orjson
import sys
import shutil
import datetime
import uuid

"""
extraction_engine.py
---------------------------------------------
Extracts Java attributes/components from a ZIP file of Java code.
Usage: python extraction_engine.py <zip_path>
Always outputs JSON files to the 'TargetDataStore' directory.
---------------------------------------------
"""

# Helper: classify layer by file path or package
def classify_layer(path_or_package):
    s = str(path_or_package).lower()
    if any(x in s for x in ["model", "entity", "domain"]):
        return "MODEL"
    if any(x in s for x in ["repo", "repository", "dao"]):
        return "REPOSITORY"
    if any(x in s for x in ["service"]):
        return "SERVICE"
    if any(x in s for x in ["controller", "rest", "api"]):
        return "CONTROLLER"
    if any(x in s for x in ["ui", "view", "page", "html", "jsp"]):
        return "UI"
    return "DEFAULT"

def extract_attributes_from_java(java_path, batch_id):
    """
    Returns a list of attribute dicts matching the required format, one per field found in the Java file.
    """
    attribute_dicts = []
    # Read the Java file
    full_source = java_path.read_text(encoding="utf-8")
    lines = full_source.splitlines()
    # Extract class name
    class_match = re.search(r'class\s+(\w+)', full_source)
    class_name = class_match.group(1) if class_match else java_path.stem
    # Extract fields: (visibility, type, name)
    fields = []
    for i, line in enumerate(lines):
        field_match = re.match(r'\s*(private|protected|public)\s+([\w<>]+)\s+([\w_]+)\s*;', line)
        if field_match:
            fields.append((field_match.group(1), field_match.group(2), field_match.group(3)))
    # Find all Java and HTML files in the project
    all_java_files = list(java_path.parent.parent.rglob("*.java"))
    all_html_files = list(java_path.parent.parent.rglob("*.html"))
    for idx, field in enumerate(fields):
        visibility, field_type, field_name = field
        line_num = None
        snippet = ""
        for i, line in enumerate(lines):
            if re.search(rf'{visibility}\s+{re.escape(field_type)}\s+{re.escape(field_name)}\s*;', line):
                line_num = i + 1
                snippet = line.strip()
                break
        annotations = []
        doc_comments = []
        if line_num is not None:
            # Parse annotations
            for j in range(line_num-2, max(line_num-6, -1), -1):
                if j >= 0:
                    ann_match = re.match(r'@([\w]+)', lines[j].strip())
                    if ann_match:
                        annotations.append(ann_match.group(1))
            # Parse Javadoc/comments above field
            for j in range(line_num-2, max(line_num-10, -1), -1):
                if j >= 0:
                    doc_match = re.match(r'/\*\*(.*?)\*/', lines[j].strip())
                    if doc_match:
                        doc_comments.append(doc_match.group(1))
                    comment_match = re.match(r'//(.*)', lines[j].strip())
                    if comment_match:
                        doc_comments.append(comment_match.group(1))
        # Aliases extraction: look for alternative names in annotations, comments, and code
        aliases = set()
        for j in range(line_num-6, line_num+2):
            if 0 <= j < len(lines):
                col_match = re.search(r'@Column\s*\(.*name\s*=\s*"([^"]+)"', lines[j])
                if col_match:
                    aliases.add(col_match.group(1))
                table_match = re.search(r'@Table\s*\(.*name\s*=\s*"([^"]+)"', lines[j])
                if table_match:
                    aliases.add(table_match.group(1))
        for j in range(line_num-6, line_num+2):
            if 0 <= j < len(lines):
                comment_match = re.search(r'//\s*alias\s*:?\s*([\w_]+)', lines[j], re.IGNORECASE)
                if comment_match:
                    aliases.add(comment_match.group(1))
        for j in range(max(0, line_num-10), min(len(lines), line_num+10)):
            if re.search(rf'{field_name}\s*[:=]\s*([\w_]+)', lines[j]):
                alt_match = re.findall(rf'{field_name}\s*[:=]\s*([\w_]+)', lines[j])
                for alt in alt_match:
                    if alt != field_name:
                        aliases.add(alt)

        components = []
        class_snippet = snippet
        explanation = f"Field {field_name} of type {field_type} in class {class_name}"
        components.append({
            "type": classify_layer(java_path),
            "filePath": str(java_path),
            "className": class_name,
            "usageType": visibility,
            "snippet": class_snippet,
            "lineRange": line_num,
            "explanation": explanation
        })
        # Scan all Java files for references to the field
        for jfile in all_java_files:
            try:
                jcontent = jfile.read_text(encoding="utf-8")
                # ...existing code...
                for m in re.finditer(rf'\b{re.escape(field_name)}\b', jcontent):
                    lines_j = jcontent.splitlines()
                    line_idx = jcontent[:m.start()].count('\n')
                    context_line = lines_j[line_idx].strip() if line_idx < len(lines_j) else ''
                    class_match_j = re.search(r'class\s+(\w+)', jcontent)
                    class_name_j = class_match_j.group(1) if class_match_j else jfile.stem
                    usage_type = "REFERENCE"
                    layer = classify_layer(jfile)
                    if jfile == java_path and context_line == class_snippet:
                        continue
                    # Detect SQL queries and ORM annotations
                    sql_match = re.search(r'(select|update|delete|insert)\s', context_line, re.IGNORECASE)
                    orm_annots = re.findall(r'@(Entity|Table|Column|Id|JoinColumn|ManyToOne|OneToMany)', jcontent)
                    components.append({
                        "type": layer,
                        "filePath": str(jfile),
                        "className": class_name_j,
                        "usageType": usage_type,
                        "snippet": context_line,
                        "lineRange": line_idx+1,
                        "explanation": f"Reference to {field_name} in class {class_name_j}",
                        "sql": bool(sql_match),
                        "orm": orm_annots
                    })
            except Exception:
                continue
        # Scan all HTML files for UI references
        for hfile in all_html_files:
            hcontent = hfile.read_text(encoding="utf-8")
            # ...existing code...
        # Scan for REST/API annotations and external calls
        for jfile in all_java_files:
            try:
                jcontent = jfile.read_text(encoding="utf-8")
            except Exception:
                continue
            rest_annots = re.findall(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping|ApiOperation)', jcontent)
            external_calls = re.findall(r'(httpClient|restTemplate|WebClient)\.(get|post|put|delete)', jcontent)
            if rest_annots:
                components.append({
                    "type": "CONTROLLER",
                    "filePath": str(jfile),
                    "className": jfile.stem,
                    "usageType": "REST_ANNOTATION",
                    "snippet": ', '.join(rest_annots),
                    "lineRange": 0,
                    "explanation": f"REST API annotation(s) in {jfile.name}"
                })
            if external_calls:
                components.append({
                    "type": "INTEGRATION",
                    "filePath": str(jfile),
                    "className": jfile.stem,
                    "usageType": "EXTERNAL_CALL",
                    "snippet": ', '.join([f'{c[0]}.{c[1]}' for c in external_calls]),
                    "lineRange": 0,
                    "explanation": f"External API call(s) in {jfile.name}"
                })
        # Build rich dependency graph
        dep_nodes = set()
        dep_edges = []
        # Add main class and field as nodes
        dep_nodes.add(class_name)
        dep_nodes.add(field_name)
        # Add nodes and edges for each component
        for comp in components:
            dep_nodes.add(comp.get("className", ""))
            dep_nodes.add(comp.get("filePath", ""))
            # Edge: declaration
            if comp["type"] == "MODEL" and comp["usageType"] in ["private", "protected", "public"]:
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "declaration",
                    "layer": comp["type"]
                })
            # Edge: repository query
            if comp["type"] == "REPOSITORY":
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "queries",
                    "layer": comp["type"]
                })
            # Edge: service call
            if comp["type"] == "SERVICE":
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "calls",
                    "layer": comp["type"]
                })
            # Edge: controller bind/write
            if comp["type"] == "CONTROLLER":
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "binds",
                    "layer": comp["type"]
                })
            # Edge: UI bind
            if comp["type"] == "UI":
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "ui-binds",
                    "layer": comp["type"]
                })
            # Edge: generic reference
            if comp["usageType"] in ["REFERENCE", "UI_REFERENCE"]:
                dep_edges.append({
                    "from": comp["className"],
                    "to": field_name,
                    "type": "refers",
                    "layer": comp["type"]
                })
        # Impact analysis extraction (output as objects with explanation, filePath, lineRange)
        impact = {
            "application": [],
            "database": [],
            "integration": [],
            "docsTesting": []
        }
        print(f"\n[DEBUG] Extracting impacts for attribute: {field_name} in class: {class_name}")
        # Application quadrant
        for comp in components:
            if comp["type"] in ["SERVICE", "CONTROLLER"]:
                impact["application"].append({
                    "explanation": f"Logic in {comp['className']} may rely on {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
                if "set" in comp.get("snippet", "").lower() or "update" in comp.get("snippet", "").lower():
                    impact["application"].append({
                        "explanation": f"Setter/update method for {field_name} in {comp['className']}",
                        "filePath": comp.get("filePath"),
                        "lineRange": comp.get("lineRange")
                    })
                if "get" in comp.get("snippet", "").lower():
                    impact["application"].append({
                        "explanation": f"Getter/accessor for {field_name} in {comp['className']}",
                        "filePath": comp.get("filePath"),
                        "lineRange": comp.get("lineRange")
                    })
            if comp["usageType"] == "REFERENCE" and comp["type"] in ["SERVICE", "CONTROLLER"]:
                impact["application"].append({
                    "explanation": f"Direct reference to {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
        print(f"[DEBUG] Application impacts: {impact['application']}")
        # Database quadrant
        for comp in components:
            if comp["type"] == "REPOSITORY":
                impact["database"].append({
                    "explanation": f"Repository {comp['className']} queries or updates {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
                if "find" in comp.get("snippet", "").lower() or "save" in comp.get("snippet", "").lower():
                    impact["database"].append({
                        "explanation": f"Repository method {comp['snippet']} interacts with {field_name}",
                        "filePath": comp.get("filePath"),
                        "lineRange": comp.get("lineRange")
                    })
            if any(kw in comp.get("snippet", "").lower() for kw in ["sql", "select", "insert", "update", "delete", "where", "from"]):
                impact["database"].append({
                    "explanation": f"SQL/ORM logic involving {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            if "@column" in comp.get("snippet", "").lower():
                impact["database"].append({
                    "explanation": f"ORM annotation {comp['snippet']} for {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
        print(f"[DEBUG] Database impacts: {impact['database']}")
        # Integration quadrant
        for comp in components:
            if comp["type"] == "CONTROLLER":
                impact["integration"].append({
                    "explanation": f"API endpoint in {comp['className']} exposes or modifies {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
                if "@getmapping" in comp.get("snippet", "").lower() or "resttemplate" in comp.get("snippet", "").lower():
                    impact["integration"].append({
                        "explanation": f"REST mapping or external API for {field_name} in {comp['className']}",
                        "filePath": comp.get("filePath"),
                        "lineRange": comp.get("lineRange")
                    })
            if comp["type"] == "INTEGRATION":
                impact["integration"].append({
                    "explanation": f"External API call {comp['snippet']} in {comp['className']} uses {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            if comp["type"] == "UI":
                impact["integration"].append({
                    "explanation": f"UI element in {comp['className']} binds to {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            if comp["usageType"] == "UI_REFERENCE":
                impact["integration"].append({
                    "explanation": f"UI reference to {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
        print(f"[DEBUG] Integration impacts: {impact['integration']}")
        # Docs/Testing quadrant
        for comp in components:
            if "test" in comp.get("className", "").lower():
                impact["docsTesting"].append({
                    "explanation": f"Test class {comp['className']} covers {field_name}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            if "@org.junit.test" in comp.get("snippet", "").lower() or "assert" in comp.get("snippet", "").lower():
                impact["docsTesting"].append({
                    "explanation": f"JUnit test for {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            if "doc" in comp.get("snippet", "").lower() or "javadoc" in comp.get("snippet", "").lower():
                impact["docsTesting"].append({
                    "explanation": f"Documentation for {field_name} in {comp['className']}",
                    "filePath": comp.get("filePath"),
                    "lineRange": comp.get("lineRange")
                })
            for comment in doc_comments:
                impact["docsTesting"].append({
                    "explanation": f"Doc comment: {comment} for {field_name} in {class_name}",
                    "filePath": str(java_path),
                    "lineRange": line_num
                })
        print(f"[DEBUG] Docs/Testing impacts: {impact['docsTesting']}")
        # Ensure all quadrants have at least a default message
        for key in ["application", "database", "integration", "docsTesting"]:
            if not impact[key]:
                impact[key].append({
                    "explanation": "No impact found for this section.",
                    "filePath": None,
                    "lineRange": None
                })
        # Process diff extraction (placeholder logic)
        # In a real scenario, you would compare with a process mapping/config
        expected_processes = [f"KYC_{field_name}_Onboarding", f"KYC_Verify_{field_name}_Format"]
        extracted_processes = []
        for comp in components:
            if "process" in comp.get("snippet", "").lower():
                extracted_processes.append(comp["snippet"])
        missing = [p for p in expected_processes if p not in extracted_processes]
        matched = [p for p in expected_processes if p in extracted_processes]
        extra = [p for p in extracted_processes if p not in expected_processes]
        process_diff = {
            "missing": missing,
            "matched": matched,
            "extra": extra
        }
        # Meta information enhancement
        # Try to get repo revision (git hash) if available
        repo_revision = None
        try:
            import subprocess
            repo_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=java_path.parent.parent, encoding="utf-8", stderr=subprocess.DEVNULL).strip()
        except Exception:
            repo_revision = "N/A"
        meta = {
            "source": str(java_path),
            "type": field_type,
            "dependency": None,
            "annotations": annotations,
            "repoRevision": repo_revision,
            "timestamp": datetime.datetime.now().isoformat()
        }
        # Remove duplicate components (use only className, type, filePath for uniqueness)
        seen = set()
        unique_components = []
        for comp in components:
            key = (comp.get("className"), comp.get("type"), comp.get("filePath"))
            if key not in seen:
                seen.add(key)
                unique_components.append(comp)
        # Remove duplicate dependency edges
        seen_edges = set()
        unique_edges = []
        for edge in dep_edges:
            key = (edge.get("from"), edge.get("to"), edge.get("type"), edge.get("layer"))
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(edge)
        attr_dict = {
            "attributeName": field_name,
            "aliases": list(aliases) if aliases else [],
            "components": unique_components,
            "dependencies": {
                "nodes": list(dep_nodes),
                "edges": unique_edges
            },
            "impact": impact,
            "processDiff": process_diff,
            "meta": meta,
            "explanation": explanation,
            "Batch_ID": batch_id,
            "created_at": datetime.datetime.now().isoformat(),
            "fullSource": full_source
        }
        attribute_dicts.append(attr_dict)
    return attribute_dicts

def scan_java_project(imports_folder: Path, output_dir: Path, batch_id: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    for java_file in imports_folder.rglob("*.java"):
        attribute_dicts = extract_attributes_from_java(java_file, batch_id)
        for attr in attribute_dicts:
            # If this is a top-level class (no fields), ensure all top-level keys are present
            if 'attributeName' not in attr:
                # Patch: set attributeName to className if missing
                if 'components' in attr and attr['components'] and 'className' in attr['components'][0]:
                    attr['attributeName'] = attr['components'][0]['className']
                else:
                    attr['attributeName'] = java_file.stem
                # Patch: add empty meta, explanation, dependencies if missing
                attr.setdefault('meta', {'type': attr['attributeName'], 'source': str(java_file), 'annotations': [], 'dependency': None})
                attr.setdefault('explanation', f"• '{attr['attributeName']}' is a top-level class.")
                attr.setdefault('dependencies', {'nodes': [attr['attributeName']], 'edges': []})
            out_file = output_dir / f"{attr['attributeName']}.json"
            with open(out_file, "wb") as f:
                f.write(orjson.dumps(attr, option=orjson.OPT_INDENT_2))


def generate_index_json(output_dir: Path):
    # Aggregate all JSON files in output_dir into index.json
    index = {}
    for json_file in output_dir.glob("*.json"):
        try:
            with open(json_file, "rb") as f:
                data = orjson.loads(f.read())
            key = data.get("attributeName") or json_file.stem
            index[key] = data
        except Exception:
            continue
    out_file = output_dir / "index.json"
    with open(out_file, "wb") as f:
        f.write(orjson.dumps(index, option=orjson.OPT_INDENT_2))

def main():
    # Automatically process all ZIP files in SourceDataStore folder
    src_dir = Path("SourceDataStore")
    processed_dir = src_dir / "processed"
    processed_dir.mkdir(exist_ok=True)
    output_dir = Path("TargetDataStore")
    temp_extract = output_dir / "_extracted"
    # Remove all data in TargetDataStore before starting extraction
    if output_dir.exists():
        for item in output_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    zip_files = list(src_dir.glob("*.zip"))
    if not zip_files:
        print("No ZIP files found in SourceDataStore folder.")
        sys.exit(1)
    # Make a static copy of the list so moved files are not retried
    batch_counter = 1
    for zip_path in zip_files[:]:
        print(f"Processing: {zip_path}")
        batch_id = f"BATCH_{batch_counter}"
        batch_counter += 1
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        temp_extract.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                safe_member = "".join(c for c in member if c.isalnum() or c in "_-./")
                if ".." in safe_member or safe_member.startswith("/"):
                    continue
                zip_ref.extract(member, temp_extract)
        scan_java_project(temp_extract, output_dir, batch_id)
        print(f"Extraction complete for {zip_path}. JSON files in: {output_dir}")
        # Validate JSON files were created and are non-empty
        json_files = list(output_dir.glob("*.json"))
        valid = False
        for jf in json_files:
            try:
                if jf.stat().st_size > 0:
                    valid = True
                    break
            except Exception:
                continue
        if valid:
            print(f"[TEST MODE] ZIP file movement to processed is muted for {zip_path}.")
        else:
            print(f"No valid JSON files created for {zip_path}. ZIP not moved.")
    # After all extraction, generate index.json
    generate_index_json(output_dir)

if __name__ == "__main__":
    main()
