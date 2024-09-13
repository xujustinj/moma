import argparse
import gdown
import os
import os.path as osp
import tarfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dir-moma", type=str, default=".data")
    args = parser.parse_args()
    dir_moma: str = args.dir_moma

    url = "https://drive.google.com/uc?id=1stizUmyHY6aNxxbxUPD5DvoibBvUrKZW"
    fname = "anns.tar.xz"

    os.makedirs(dir_moma, exist_ok=True)
    gdown.download(url, osp.join(dir_moma, fname), quiet=False)

    file = tarfile.open(osp.join(dir_moma, fname))
    file.extractall(args.dir_moma)
    file.close()
    os.remove(osp.join(args.dir_moma, fname))


if __name__ == "__main__":
    main()
