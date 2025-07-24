#!/usr/bin/env python3
"""
Test streaming disconnect with a longer request to ensure true streaming behavior
"""

import asyncio
import subprocess
import json
import time

async def test_long_streaming_disconnect():
    """Test canceling a long streaming request to verify disconnect detection"""
    
    print("🧪 Testing streaming disconnect with long request...")
    
    # Create curl command for a very long streaming request
    curl_cmd = [
        'curl', '-X', 'POST', 
        'http://localhost:9090/v1/messages',
        '-H', 'Content-Type: application/json',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', json.dumps({
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "请写一篇5000字的详细文章，详细介绍人工智能的发展历史，包括每个重要节点、关键人物、技术突破等，要求内容丰富详实，分段清晰。"}],
            "max_tokens": 2000,
            "stream": True
        }),
        '--no-buffer'
    ]
    
    print("📡 Starting long streaming request...")
    start_time = time.time()
    
    # Start curl process
    process = subprocess.Popen(
        curl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("⏰ Waiting 2 seconds, then canceling to test mid-stream disconnect...")
    await asyncio.sleep(2)
    
    cancel_time = time.time()
    print(f"🔌 Canceling request after {cancel_time - start_time:.1f} seconds...")
    process.terminate()
    
    # Wait for process to end
    try:
        stdout, stderr = process.communicate(timeout=3)
        end_time = time.time()
        print(f"✅ Process ended after {end_time - start_time:.1f} seconds total")
        print(f"📤 Exit code: {process.returncode}")
        if stdout:
            print(f"📄 Received {len(stdout)} chars of output")
            # Show first few chunks to verify streaming
            lines = stdout.split('\n')[:10]
            print("📋 First few response lines:")
            for i, line in enumerate(lines):
                if line.strip():
                    print(f"  {i+1}. {line[:100]}...")
    except subprocess.TimeoutExpired:
        print("⚠️  Process didn't terminate, killing...")
        process.kill()
        stdout, stderr = process.communicate()
    
    print("\n" + "="*60)
    print("🔍 Expected logs for streaming disconnect:")
    print("1. client_added_to_broadcaster")
    print("2. parallel_broadcast_started") 
    print("3. chunk_yielded_to_original_client (multiple chunks)")
    print("4. original_client_disconnected_during_yield")
    print("5. stopping_no_duplicate_clients")
    print("6. broadcast_session_summary")
    print("="*60)
    print("📋 Check logs with:")
    print("tail -30 server.log | grep -E '(req_id.*[a-f0-9]{8}|disconnect|chunk_yielded|broadcast)'")

if __name__ == "__main__":
    asyncio.run(test_long_streaming_disconnect())