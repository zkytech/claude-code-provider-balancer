#!/usr/bin/env python3
"""
Test mid-stream duplicate request handling
"""

import asyncio
import subprocess
import json
import time
import threading

async def test_midstream_duplicate():
    """Test scenario where duplicate request arrives while original is streaming"""
    
    print("🧪 Testing mid-stream duplicate request handling...")
    
    # Request that should generate a long streaming response
    request_payload = {
        "model": "claude-3-5-haiku-20241022",
        "messages": [{"role": "user", "content": "请详细解释什么是人工智能，包括其历史发展、主要技术、应用领域等。请写得详细一些。"}],
        "max_tokens": 1500,
        "stream": True
    }
    
    # Create curl command
    def create_curl_cmd(request_name):
        return [
            'curl', '-X', 'POST', 
            'http://localhost:9090/v1/messages',
            '-H', 'Content-Type: application/json',
            '-H', 'anthropic-version: 2023-06-01',
            '-d', json.dumps(request_payload),
            '-H', f'X-Request-Name: {request_name}',  # Add identifier
            '--no-buffer'
        ]
    
    print("📡 Starting original stream request...")
    start_time = time.time()
    
    # Start original request
    original_process = subprocess.Popen(
        create_curl_cmd("original"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print(f"⏰ Waiting 2 seconds for original stream to start...")
    await asyncio.sleep(2)
    
    duplicate_start_time = time.time()
    print(f"📡 Starting duplicate request after {duplicate_start_time - start_time:.1f}s...")
    
    # Start duplicate request
    duplicate_process = subprocess.Popen(
        create_curl_cmd("duplicate"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("⏰ Letting both requests run for 3 more seconds...")
    await asyncio.sleep(3)
    
    end_time = time.time()
    print(f"🔄 Terminating both requests after {end_time - start_time:.1f}s total...")
    
    # Terminate both processes
    original_process.terminate()
    duplicate_process.terminate()
    
    # Collect results
    try:
        original_stdout, original_stderr = original_process.communicate(timeout=2)
        duplicate_stdout, duplicate_stderr = duplicate_process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        original_process.kill()
        duplicate_process.kill()
        original_stdout, original_stderr = original_process.communicate()
        duplicate_stdout, duplicate_stderr = duplicate_process.communicate()
    
    print(f"\n{'='*60}")
    print("📊 Results Summary:")
    print(f"⏱️  Total test time: {end_time - start_time:.1f}s")
    print(f"📤 Original exit code: {original_process.returncode}")
    print(f"📤 Duplicate exit code: {duplicate_process.returncode}")
    
    if original_stdout:
        original_chunks = len([line for line in original_stdout.split('\n') if line.strip().startswith('data:')])
        print(f"📄 Original received ~{original_chunks} data chunks, {len(original_stdout)} chars")
    
    if duplicate_stdout:
        duplicate_chunks = len([line for line in duplicate_stdout.split('\n') if line.strip().startswith('data:')])
        print(f"📄 Duplicate received ~{duplicate_chunks} data chunks, {len(duplicate_stdout)} chars")
        
        # Check if duplicate response starts with same content as original
        if original_stdout and duplicate_stdout:
            # Extract first few data lines for comparison
            orig_lines = [line for line in original_stdout.split('\n')[:10] if 'data:' in line]
            dup_lines = [line for line in duplicate_stdout.split('\n')[:10] if 'data:' in line]
            
            if orig_lines and dup_lines:
                first_match = orig_lines[0] == dup_lines[0] if len(orig_lines) > 0 and len(dup_lines) > 0 else False
                print(f"🔍 First chunk matches: {first_match}")
    
    print(f"\n{'='*60}")
    print("🔍 Expected logs to check:")
    print("1. broadcaster_registered - Original stream registers broadcaster")
    print("2. duplicate_request_found_active_broadcaster - Duplicate finds active broadcaster")  
    print("3. historical_chunk_yielded_to_duplicate - Duplicate gets past chunks")
    print("4. live_chunk_yielded_to_duplicate - Duplicate gets new chunks")
    print("5. broadcaster_unregistered - Broadcaster cleaned up when done")
    print(f"{'='*60}")
    print("📋 Check logs with:")
    print("tail -50 server.log | grep -E '(broadcaster|duplicate|historical|live_chunk)'")

if __name__ == "__main__":
    asyncio.run(test_midstream_duplicate())