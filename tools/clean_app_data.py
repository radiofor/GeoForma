"""Inspect or clean expired, recognized resource remnants; dry-run by default."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--only-model',help='Limit cleanup to one catalog model filename')
    args=parser.parse_args()
    from geoforma.housekeeping import clean_download_remnants
    class Task:
        def check(self):pass
    print(json.dumps(clean_download_remnants(args.data_root,Task(),apply=args.apply,only_model=args.only_model),ensure_ascii=False))


if __name__=='__main__':main()
