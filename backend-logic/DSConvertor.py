#Support for this file has been replaced on a separate repo.

import fixeddslogparser.dslogstream as dslp
from pathlib import Path
import os
import csv

class DSConvertor:
    def __init__(self, dsLogDir=""):
        self.dsLogDir = dsLogDir
        self.destinationDr = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "csvDSLogs"
        )
        self.exclusionListFP = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "exclusionListFP.txt"
        )

        # Ensure output directory exists
        os.makedirs(self.destinationDr, exist_ok=True)

        # Ensure exclusion file exists
        if not os.path.exists(self.exclusionListFP):
            Path(self.exclusionListFP).touch()

    def processDSLogs(self):
        for file in os.listdir(self.dsLogDir)[:2]:
            file_path = os.path.join(self.dsLogDir, file)

            # Only process .dslog files not already excluded
            with open(self.exclusionListFP, "r") as exF:
                exclusions = exF.read().splitlines()

            if file.endswith(".dslog") and file not in exclusions:
                print(f"[*] Processing {file}...")

                try:
                    # Parse DS log
                    newDSLP = dslp.DSLogParser(file_path)
                    records = list(newDSLP.read_records())

                    # Skip if nothing parsed
                    if not records:
                        print(f"[!] No records found in {file}")
                        continue

                    # Write to CSV
                    csv_filename = file[:-6] + ".csv"
                    csv_path = os.path.join(self.destinationDr, csv_filename)

                        # Define all expected CSV fields, including PDP data
                    fieldnames = [
                        "time", "round_trip_time", "packet_loss", "voltage",
                        "rio_cpu", "can_usage", "wifi_db", "bandwidth",
                        "robot_disabled", "robot_auto", "robot_tele",
                        "ds_disabled", "ds_auto", "ds_tele",
                        "watchdog", "brownout",
                        "pdp_id", "pdp_currents", "pdp_resistance",
                        "pdp_voltage", "pdp_temp", "pdp_total_current"
                    ]

                    with open(csv_path, "w", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(records)


                    print(f"[+] Wrote {csv_filename} with {len(records)} records.")
                    self.addToExclusionList(file)

                except Exception as e:
                    print(f"[!] Failed to process {file}: {e}")

    def addToExclusionList(self, fileName=""):
        with open(self.exclusionListFP, "a") as f:
            f.write(fileName + "\n")


# Update this path to where your .dslog files are stored
dslogdir = r"/Users/jacksonyoes/Downloads/dslogs"

dsconv = DSConvertor(dslogdir)
dsconv.processDSLogs()
