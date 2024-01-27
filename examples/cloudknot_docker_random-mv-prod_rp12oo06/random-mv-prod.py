import boto3
import cloudpickle
import os
import pickle
from argparse import ArgumentParser
from functools import wraps


def pickle_to_s3(server_side_encryption=None, array_job=True):
    def real_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            s3 = boto3.client("s3")
            bucket = os.environ.get("CLOUDKNOT_JOBS_S3_BUCKET")

            if array_job:
                array_index = os.environ.get("AWS_BATCH_JOB_ARRAY_INDEX")
            else:
                array_index = "0"

            jobid = os.environ.get("AWS_BATCH_JOB_ID")

            if array_job:
                jobid = jobid.split(":")[0]

            key = "/".join(
                [
                    "cloudknot.jobs",
                    os.environ.get("CLOUDKNOT_S3_JOBDEF_KEY"),
                    jobid,
                    array_index,
                    "{0:03d}".format(int(os.environ.get("AWS_BATCH_JOB_ATTEMPT"))),
                    "output.pickle",
                ]
            )

            result = f(*args, **kwargs)

            # Only pickle output and write to S3 if it is not None
            if result is not None:
                pickled_result = cloudpickle.dumps(result, protocol=3)
                if server_side_encryption is None:
                    s3.put_object(Bucket=bucket, Body=pickled_result, Key=key)
                else:
                    s3.put_object(
                        Bucket=bucket,
                        Body=pickled_result,
                        Key=key,
                        ServerSideEncryption=server_side_encryption,
                    )

        return wrapper

    return real_decorator


def random_mv_prod(b):    
    import numpy as np
    import pandas as pd
    import s3fs
    import json
    import logging
    import os.path as op
    import nibabel as nib
    import dipy.data as dpd
    import dipy.tracking.utils as dtu
    import dipy.tracking.streamline as dts
    from dipy.io.streamline import save_tractogram, load_tractogram
    from dipy.stats.analysis import afq_profile, gaussian_weights
    from dipy.io.stateful_tractogram import StatefulTractogram
    from dipy.io.stateful_tractogram import Space
    import dipy.core.gradients as dpg
    from dipy.segment.mask import median_otsu
    
    x = np.random.normal(0, b, 1024)
    A = np.random.normal(0, b, (1024, 1024))
    
    return np.dot(A, x)


if __name__ == "__main__":
    description = (
        "Download input from an S3 bucket and provide that input "
        "to our function. On return put output in an S3 bucket."
    )

    parser = ArgumentParser(description=description)

    parser.add_argument(
        "bucket",
        metavar="bucket",
        type=str,
        help="The S3 bucket for pulling input and pushing output.",
    )

    parser.add_argument(
        "--starmap",
        action="store_true",
        help="Assume input has already been grouped into a single tuple.",
    )

    parser.add_argument(
        "--arrayjob",
        action="store_true",
        help="If True, this is an array job and it should reference the "
        "AWS_BATCH_JOB_ARRAY_INDEX environment variable.",
    )

    parser.add_argument(
        "--sse",
        dest="sse",
        action="store",
        choices=["AES256", "aws:kms"],
        default=None,
        help="Server side encryption algorithm used when storing objects in S3.",
    )

    args = parser.parse_args()

    s3 = boto3.client("s3")
    bucket = args.bucket

    jobid = os.environ.get("AWS_BATCH_JOB_ID")

    if args.arrayjob:
        jobid = jobid.split(":")[0]

    key = "/".join(
        [
            "cloudknot.jobs",
            os.environ.get("CLOUDKNOT_S3_JOBDEF_KEY"),
            jobid,
            "input.pickle",
        ]
    )

    response = s3.get_object(Bucket=bucket, Key=key)
    input_ = pickle.loads(response.get("Body").read())

    if args.arrayjob:
        array_index = int(os.environ.get("AWS_BATCH_JOB_ARRAY_INDEX"))
        input_ = input_[array_index]

    if args.starmap:
        pickle_to_s3(args.sse, args.arrayjob)(random_mv_prod)(*input_)
    else:
        pickle_to_s3(args.sse, args.arrayjob)(random_mv_prod)(input_)
