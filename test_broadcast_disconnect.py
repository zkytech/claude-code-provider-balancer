#!/usr/bin/env python3
"""
Test client disconnect with new parallel broadcaster
"""

import asyncio
import subprocess
import json
import time

async def test_3s_cancel():
    """Test canceling request after 3 seconds"""
    
    print("🧪 Testing client disconnect with parallel broadcaster...")
    
    # Create curl command for streaming request
    curl_cmd = [
        'curl', '-X', 'POST', 
        'http://localhost:9090/v1/messages',
        '-H', 'Content-Type: application/json',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', json.dumps({
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "写一个长文章关于人工智能的发展历史"}],
            "max_tokens": 1000,
            "stream": True
        }),
        '--no-buffer'
    ]
    
    print("📡 Starting request...")
    start_time = time.time()
    
    # Start curl process
    process = subprocess.Popen(
        curl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("⏰ Request started, waiting 3 seconds before canceling...")
    await asyncio.sleep(3)
    
    cancel_time = time.time()
    print(f"🔌 Canceling request after {cancel_time - start_time:.1f} seconds...")
    process.terminate()
    
    # Wait for process to end
    try:
        stdout, stderr = process.communicate(timeout=2)
        end_time = time.time()
        print(f"✅ Process ended after {end_time - start_time:.1f} seconds total")
        print(f"📤 Exit code: {process.returncode}")
        if stdout:
            print(f"📄 Received {len(stdout)} chars of output")
    except subprocess.TimeoutExpired:
        print("⚠️  Process didn't terminate, killing...")
        process.kill()
        stdout, stderr = process.communicate()
    
    print("\n" + "="*50)
    print("🔍 Expected logs in broadcast system:")
    print("- client_added_to_broadcaster")
    print("- parallel_broadcast_started") 
    print("- chunk_prepared_for_client")
    print("- broadcast_chunk_completed")
    print("- original_client_disconnected_during_yield")
    print("- broadcast_session_summary")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_3s_cancel())