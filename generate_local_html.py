#!/usr/bin/env python3
"""
Generate a local HTML file that embeds the JSON data directly
This allows the HTML to work without needing a web server
"""

import json
import os
from pathlib import Path

def generate_local_html():
    # Read the original HTML file
    html_file = Path("home.html")
    index_json_file = Path("TargetDataStore/index.json")
    
    if not html_file.exists():
        print(f"Error: {html_file} not found")
        return
    
    if not index_json_file.exists():
        print(f"Error: {index_json_file} not found")
        return
    
    # Read the HTML content
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Read the JSON data
    with open(index_json_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # Convert JSON to JavaScript variable
    json_js = json.dumps(json_data, indent=2)
    
    # Create the embedded script
    embedded_script = f"""
<script>
// Embedded JSON data for local usage
window.EMBEDDED_INDEX_DATA = {json_js};
</script>
"""
    
    # Find where to insert the script (before the closing </head> tag)
    head_close_pos = html_content.find('</head>')
    if head_close_pos == -1:
        print("Error: Could not find </head> tag in HTML")
        return
    
    # Insert the embedded script
    new_html = html_content[:head_close_pos] + embedded_script + html_content[head_close_pos:]
    
    # Replace the loadAttributes function to use embedded data
    old_load_function = """async function loadAttributes() {
    try {
    console.log('[DEBUG] Fetching /TargetDataStore/index.json...');
    const indexResp = await fetch('TargetDataStore/index.json');
    console.log('[DEBUG] index.json fetch status:', indexResp.status);
    const indexText = await indexResp.text();
    console.log('[DEBUG] index.json raw text:', indexText.slice(0, 500));
        let indexData;
        try {
            indexData = JSON.parse(indexText);
        } catch (jsonErr) {
            console.error('[DEBUG] Failed to parse index.json:', jsonErr);
            throw jsonErr;
        }"""
    
    new_load_function = """async function loadAttributes() {
    try {
        console.log('[DEBUG] Using embedded JSON data...');
        let indexData;
        if (window.EMBEDDED_INDEX_DATA) {
            indexData = window.EMBEDDED_INDEX_DATA;
            console.log('[DEBUG] Loaded embedded data successfully');
        } else {
            // Fallback to fetch if embedded data is not available
            console.log('[DEBUG] Fetching /TargetDataStore/index.json...');
            const indexResp = await fetch('TargetDataStore/index.json');
            console.log('[DEBUG] index.json fetch status:', indexResp.status);
            const indexText = await indexResp.text();
            console.log('[DEBUG] index.json raw text:', indexText.slice(0, 500));
            try {
                indexData = JSON.parse(indexText);
            } catch (jsonErr) {
                console.error('[DEBUG] Failed to parse index.json:', jsonErr);
                throw jsonErr;
            }
        }"""
    
    # Replace the function
    new_html = new_html.replace(old_load_function, new_load_function)
    
    # Write the new HTML file
    output_file = Path("home_local.html")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"✅ Generated {output_file}")
    print(f"📁 File size: {os.path.getsize(output_file) / 1024 / 1024:.1f} MB")
    print(f"🌐 You can now open {output_file} directly in your browser!")
    print(f"💡 The file works locally without needing a web server.")

if __name__ == "__main__":
    generate_local_html()