#!/bin/bash

# Path to the gurobi.lic file
LIC_FILE="/opt/gurobi/gurobi.lic"

# Check if the LIC_FILE exists, if not create it
if [ ! -f "$LIC_FILE" ]; then
    echo "Creating $LIC_FILE"
    mkdir -p "$(dirname "$LIC_FILE")"
    touch "$LIC_FILE"
    # Add license data from environment variables
    echo "WLSACCESSID=${GRB_WLSACCESSID}" >> "$LIC_FILE"
    echo "WLSSECRET=${GRB_WLSSECRET}" >> "$LIC_FILE"
    echo "LICENSEID=${GRB_LICENSEID}" >> "$LIC_FILE"
fi

# Run tests
pytest "$@"