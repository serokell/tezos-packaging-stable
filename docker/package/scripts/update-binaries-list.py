import os
import sys
import json

binaries_json_path = "/tezos-packiging/docker/test/binaries.json"

def update_binaries(binaries, field):
    with open(binaries_json_path, 'r') as file:
        data = json.load(file)

    data[field] = binaries
    with open(binaries_json_path, 'w') as file:
        json.dump(data, file, indent=4)


def main():
    if len(sys.argv) < 3:
        print("You need to provide tag and path to list of binaries argument")
        return
    tag = sys.argv[1]

    binaries = []
    with open(sys.argv[2], 'r') as f:
        binaries = [l.strip() for l in f.readlines()]

    if not binaries:
        raise Exception('Exception, while reading binaries list: binaries list is empty')

    field = 'released'
    if 'rc' in tag:
        field = 'candidates'

    update_binaries(binaries, field)


if __name__ == '__main__':
    main()

