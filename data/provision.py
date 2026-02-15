import csv, json
import sys
import argparse
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
PMACS_FILE = os.path.join(DATA_DIR, "pmacs.csv")
SMACS_FILE = os.path.join(DATA_DIR, "smacs.csv")
TEST_PIDS_FILE = os.path.join(DATA_DIR, "test_pids.csv")
TEST_GIDS_FILE = os.path.join(DATA_DIR, "test_gids.csv")


def load_csv(filepath):
    data = []
    if not os.path.exists(filepath):
        print(f"Warning: File not found {filepath}")
        return data
    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def get_mappings():
    pmacs = {row["pmac"]: row["pid"] for row in load_csv(PMACS_FILE)}
    smacs = {row["smac"]: row["sid"] for row in load_csv(SMACS_FILE)}
    gids = {row["gid"].upper(): row["color"] for row in load_csv(TEST_GIDS_FILE)}
    return pmacs, smacs, gids


def lookup(mac):
    pmacs, smacs, gids = get_mappings()
    # Normalize MAC
    mac_norm = mac.replace(":", "").upper()

    # Check PMACS (Pole IDs)
    for pmac, pid in pmacs.items():
        if pmac.replace(":", "").upper() == mac_norm:
            result = f"Found PID: {pid} for MAC: {pmac}"
            # Enrich with test data if available
            test_data = load_csv(TEST_PIDS_FILE)
            for row in test_data:
                # Normalize both and check if one is a suffix of the other (test data often omits prefix)
                norm_row = row["pmac"].replace(":", "").upper()
                norm_factory = pmac.replace(":", "").upper()
                if norm_row in norm_factory or norm_factory in norm_row:
                    color = gids.get(row["gid"].upper(), "unknown")
                    result += f"\nDeployment: Booth {row['bid']}, Slave {row['sid']}, Group {row['gid']} ({color})"
            return result

    # Check SMACS (Slave IDs)
    for smac, sid in smacs.items():
        if smac.upper() == mac_norm:
            return f"Found SID: {sid} for MAC: {smac}"

    return f"MAC address {mac} not found in factory mappings."


def generate_pillars():
    pmacs, smacs, gids = get_mappings()
    test_data = load_csv(TEST_PIDS_FILE)

    pillars = []
    for row in test_data:
        # gid,sid,bid,pmac,pid
        factory_pid = pmacs.get(row["pmac"])
        if factory_pid and factory_pid != row["pid"]:
            print(
                f"Warning: Mismatch for PMAC {row['pmac']}. Factory PID: {factory_pid}, Test PID: {row['pid']}"
            )

        row["color"] = gids.get(row["gid"].upper(), "unknown")
        pillars.append(row)

    return pillars


def main():
    parser = argparse.ArgumentParser(description="NNARA Provisioning Utility")
    parser.add_argument("--lookup", help="Lookup PID/SID by MAC address")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify test_pids.csv against factory mappings",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write pmacs_sid.csv",
    )
    args = parser.parse_args()

    if args.lookup:
        print(lookup(args.lookup))
    elif args.verify:
        s = {}
        pillars = generate_pillars()
        print(f"Verified {type(pillars)} with {len(pillars)} records.")
        # print(pillars)
        for p in [p for p in pillars if p["sid"] == "S1"]:
            print(p["pid"], p["pmac"])
            s[p["pid"]] = p["pmac"]
        print(s)

    elif args.write:
        pillars = generate_pillars()
        for sid in set(row["sid"] for row in pillars):
            s = {}
            for p in [p for p in pillars if p["sid"] == sid]:
                # print(p["pid"], p["pmac"])
                s[p["pid"]] = p["pmac"]
            json.dump(s, open(f"pids_{sid[1:]}.json", "w"))
            print(s)

            # csvfile = f"pmacs_{sid}.csv"
            # with open(csvfile, "w", newline="") as csvfile:
            #     fieldnames = ["pid", "pmac", "bid"]
            #     writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            #     writer.writeheader()
            #     for p in [p for p in pillars if p["sid"] == sid]:
            #         writer.writerow(
            #             {
            #                 "pid": p["pid"],
            #                 "pmac": p["pmac"],
            #                 "bid": p["bid"],
            #             }
            #         )
            # print(f"Wrote {csvfile}.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
