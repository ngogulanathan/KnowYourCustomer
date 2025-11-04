#!/usr/bin/env python3
"""
Generate a lightweight local HTML file with external JSON loading fallback
This creates a smaller file that can work both locally and with a server
"""

import json
from pathlib import Path

def generate_lightweight_local_html():
    # Read the original HTML file
    html_file = Path("home.html")
    
    if not html_file.exists():
        print(f"Error: {html_file} not found")
        return
    
    # Read the HTML content
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Create a more sophisticated load function that works offline
    new_load_function = """async function loadAttributes() {
    try {
        console.log('[DEBUG] Attempting to load attributes...');
        let indexData;
        
        // First try: Check if data is embedded (for local usage)
        if (window.EMBEDDED_INDEX_DATA) {
            console.log('[DEBUG] Using embedded JSON data...');
            indexData = window.EMBEDDED_INDEX_DATA;
        } else {
            // Second try: Fetch from server (if available)
            try {
                console.log('[DEBUG] Fetching /TargetDataStore/index.json...');
                const indexResp = await fetch('TargetDataStore/index.json');
                console.log('[DEBUG] index.json fetch status:', indexResp.status);
                
                if (indexResp.ok) {
                    const indexText = await indexResp.text();
                    console.log('[DEBUG] index.json raw text:', indexText.slice(0, 500));
                    indexData = JSON.parse(indexText);
                } else {
                    throw new Error(`HTTP ${indexResp.status}`);
                }
            } catch (fetchErr) {
                console.warn('[DEBUG] Fetch failed:', fetchErr);
                // Third try: Load from local file path (if user allows)
                throw new Error('Could not load data. Please either: 1) Use home_local.html for offline usage, or 2) Run a local server for this file.');
            }
        }"""
    
    # Find and replace the loadAttributes function
    start_marker = "async function loadAttributes() {"
    end_marker = "console.log('[DEBUG] Parsed index.json:', indexData);"
    
    start_pos = html_content.find(start_marker)
    if start_pos == -1:
        print("Error: Could not find loadAttributes function")
        return
    
    end_pos = html_content.find(end_marker, start_pos)
    if end_pos == -1:
        print("Error: Could not find end of loadAttributes function")
        return
    
    # Keep the rest of the function intact
    end_pos = end_pos + len(end_marker)
    
    # Replace the function
    new_html = (html_content[:start_pos] + 
                new_load_function + 
                "\n        console.log('[DEBUG] Parsed index.json:', indexData);" + 
                html_content[end_pos:])
    
    # Write the new HTML file
    output_file = Path("home_flexible.html")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"✅ Generated {output_file}")
    print(f"📁 File size: {len(new_html) / 1024:.1f} KB")
    print(f"🔧 This version provides helpful error messages and works with both approaches.")

if __name__ == "__main__":
    generate_lightweight_local_html()