import fileinput
import io
import json
import operator
import subprocess
import sys
from datetime import datetime, timezone


def safe_get(data, keys, default=None):
    """Safely get a nested key from a dictionary."""
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def parse_timestamp(ts_str):
    """Parse ISO timestamp string into a datetime object."""
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except ValueError:
        print(f"Warning: Could not parse timestamp '{ts_str}'", file=sys.stderr)
        return datetime.min.replace(tzinfo=timezone.utc)


def run_pager(text_content):
    """Pipe text content to a pager like less or batcat."""
    pager_cmd = ["less", "-R"]

    try:
        process = subprocess.Popen(
            pager_cmd, stdin=subprocess.PIPE, universal_newlines=True
        )
        process.communicate(input=text_content)
    except FileNotFoundError:
        print(
            f"Error: Pager command '{pager_cmd[0]}' not found. Printing directly.",
            file=sys.stderr,
        )
        print(text_content)
    except BrokenPipeError:
        pass


def main():
    request_starts = {}
    all_lines = []

    print("Reading logs and finding request IDs...", file=sys.stderr)
    try:
        for line in fileinput.input():
            all_lines.append(line)
            try:
                log_entry = json.loads(line)
                req_id = safe_get(log_entry, ["detail", "request_id"])
                timestamp_str = log_entry.get("timestamp")

                if req_id and timestamp_str:
                    timestamp = parse_timestamp(timestamp_str)
                    if req_id not in request_starts:
                        request_starts[req_id] = timestamp
                    else:
                        if timestamp < request_starts[req_id]:
                            request_starts[req_id] = timestamp

            except json.JSONDecodeError:
                print(
                    f"Warning: Skipping invalid JSON line: {line.strip()}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"Warning: Error processing line: {e} - {line.strip()}",
                    file=sys.stderr,
                )

    except FileNotFoundError:
        print("Error: Input file not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"An unexpected error occurred during input reading: {e}", file=sys.stderr
        )
        sys.exit(1)

    if not request_starts:
        print("No log entries with 'detail.request_id' found.", file=sys.stderr)
        sys.exit(0)

    sorted_requests = sorted(
        request_starts.items(),
        key=operator.itemgetter(1),
        reverse=True,
    )

    print("\nAvailable Request IDs (most recent first):", file=sys.stderr)
    for i, (req_id, ts) in enumerate(sorted_requests):
        ts_display = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
        print(f"  {i + 1}: {req_id} (started around {ts_display})", file=sys.stderr)

    selected_index = 0
    while True:
        try:
            choice = input(
                f"Enter number to view logs (1-{len(sorted_requests)}) [default: 1]: "
            )
            if not choice:
                selected_index = 0
                break
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(sorted_requests):
                break
            else:
                print(
                    "Invalid choice. Please enter a number from the list.",
                    file=sys.stderr,
                )
        except ValueError:
            print("Invalid input. Please enter a number.", file=sys.stderr)
        except EOFError:
            print("\nNo selection made. Exiting.", file=sys.stderr)
            sys.exit(0)

    selected_request_id = sorted_requests[selected_index][0]
    print(f"\nFetching logs for request_id: {selected_request_id}", file=sys.stderr)

    matching_logs = []
    for line in all_lines:
        try:
            log_entry = json.loads(line)
            req_id = safe_get(log_entry, ["detail", "request_id"])
            timestamp_str = log_entry.get("timestamp")

            if req_id == selected_request_id and timestamp_str:
                timestamp = parse_timestamp(timestamp_str)
                matching_logs.append((timestamp, line))

        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    matching_logs.sort(key=operator.itemgetter(0))

    output_buffer = io.StringIO()
    for _, line_str in matching_logs:
        try:
            parsed = json.loads(line_str)
            output_buffer.write(json.dumps(parsed, indent=2))
            output_buffer.write("\n")
        except json.JSONDecodeError:
            output_buffer.write(line_str)

    print(f"Displaying {len(matching_logs)} log entries...", file=sys.stderr)
    run_pager(output_buffer.getvalue())
    output_buffer.close()


if __name__ == "__main__":
    main()
