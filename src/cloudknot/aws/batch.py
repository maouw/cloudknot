import logging
import pickle
import time
from typing import NamedTuple
from collections.abc import Mapping
from typing import Any, Optional
import cloudpickle

import cloudknot.config

from ..dockerimage import DEFAULT_PICKLE_PROTOCOL
from .base_classes import (
    BatchJobFailedError,
    CKTimeoutError,
    CloudknotInputError,
    NamedObject,
    ResourceClobberedException,
    ResourceDoesNotExistException,
    clients,
    get_s3_params,
)

__all__ = ["BatchJob", "JobExists", "JobDef"]
mod_logger = logging.getLogger(__name__)


class JobDef(NamedTuple):
    """NamedTuple for returning information about an existing AWS Batch job definition."""

    name: str
    arn: str
    output_bucket: Optional[str]
    retries: int


class JobExists(NamedTuple):
    """NamedTuple for returning information about an existing AWS Batch job."""

    exists: bool
    name: Optional[str] = None
    job_id: Optional[str] = None
    job_queue_arn: Optional[str] = None
    job_definition: Optional[JobDef] = None
    environment_variables: Optional[list[Mapping]] = None
    array_job: Optional[bool] = None


def _exists_already(job_id: str) -> JobExists:
    """
    Check if an AWS batch job exists already.

    If batch job exists, return NamedTuple with batch job info.
    Otherwise, set the NamedTuple's `exists` field to
    `False`. The remaining fields default to `None`.

    Returns
    -------
    JobExists
        A NamedTuple with fields ('exists', 'name', 'job_id', 'job_queue_arn', 'job_definition',
         'environment_variables', 'array_job')
    """
    response = clients.batch.describe_jobs(jobs=[job_id])

    if response.get("jobs"):
        job = response.get("jobs")[0]
        name = job["jobName"]
        job_queue_arn = job["jobQueue"]
        job_def_arn = job["jobDefinition"]
        environment_variables = job["container"]["environment"]

        array_job = "arrayProperties" in job

        response = clients.batch.describe_job_definitions(jobDefinitions=[job_def_arn])
        job_def = response.get("jobDefinitions")[0]
        bucket_env = [
            e
            for e in (job_def["containerProperties"]["environment"])
            if e["name"] == "CLOUDKNOT_JOBS_S3_BUCKET"
        ]
        job_definition = JobDef(
            name=job_def["jobDefinitionName"],
            arn=job_def_arn,
            output_bucket=(bucket_env[0]["value"] if bucket_env else None),
            retries=job_def["retryStrategy"]["attempts"],
        )

        mod_logger.info("Job {id:s} exists.".format(id=job_id))

        return JobExists(
            exists=True,
            name=name,
            job_id=job_id,
            job_queue_arn=job_queue_arn,
            job_definition=job_definition,
            environment_variables=environment_variables,
            array_job=array_job,
        )
    return JobExists(exists=False)


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class BatchJob(NamedObject):
    """Class for defining AWS Batch Job."""

    def __init__(
        self,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        job_queue: Optional[str] = None,
        job_definition: Optional[JobDef] = None,
        input_: Any = None,
        starmap: bool = False,
        environment_variables: Optional[list[dict]] = None,
        array_job: bool = True,
    ):
        """Initialize an AWS Batch Job object.

        If requesting information on a pre-existing job, `job_id` is required.
        Otherwise, `name`, `job_queue`, and `job_definition` are required to
        submit a new job.

        Parameters
        ----------
        job_id: string
            The AWS jobID, if requesting a job that already exists

        name : str
            Name of the job.
            Must satisfy regular expression pattern: [a-zA-Z][-a-zA-Z0-9]*

        job_queue : str
            Job queue ARN specifying the job queue to which this job
            will be submitted

        job_definition : JobDef
            Specifies the job definition on which to base this job.
            Must contain fields 'name', 'arn', 'output_bucket', and 'retries'

        input_ :
            The input to be pickled and sent to the batch job via S3

        starmap : bool
            If True, assume input is already grouped in
            tuples from a single iterable.

        environment_variables : list[dict]
            List of key/value pairs representing environment variables
            sent to the container

        array_job : bool
            If True, this batch job will be an array_job.
            Default: True
        """
        has_input = input_ is not None
        if not (job_id or all([name, job_queue, has_input, job_definition])):
            raise CloudknotInputError(
                "You must supply either job_id or "
                "(name, input_, job_queue, and "
                "job_definition)."
            )

        if job_id and any([name, job_queue, has_input, job_definition]):
            raise CloudknotInputError(
                "You may supply either job_id or (name, input_, job_queue, "
                "and job_definition), not both."
            )

        self._starmap = starmap

        if job_id:
            job = _exists_already(job_id=job_id)
            if not job.exists:
                raise ResourceDoesNotExistException(
                    "jobId {id:s} does not exists".format(id=job_id), job_id
                )

            super().__init__(name=job.name)

            self._job_queue_arn = job.job_queue_arn
            self._job_definition = job.job_definition
            self._environment_variables = job.environment_variables
            self._job_id = job.job_id
            self._array_job = job.array_job

            bucket = self._job_definition.output_bucket if self._job_definition else None
            key = "/".join(
                [
                    "cloudknot.jobs",
                    self._job_definition.name,
                    self._job_id,
                    "input.pickle",
                ]
            )

            try:
                response = clients.s3.get_object(Bucket=bucket, Key=key)
                self._input = pickle.loads(response.get("Body").read())
            except (
                clients.s3.exceptions.NoSuchBucket,
                clients.s3.exceptions.NoSuchKey,
            ):
                self._input = None

            self._section_name = self._get_section_name("batch-jobs")
            cloudknot.config.add_resource(self._section_name, self.job_id, self.name)

            mod_logger.info(
                "Retrieved pre-existing batch job {id:s}".format(id=self.job_id)
            )
        else:
            super().__init__(name=name)

            if not isinstance(job_queue, str):
                raise CloudknotInputError("job_queue must be a string.")

            self._job_queue_arn = job_queue
            if missing_attributes := {"name", "arn", "output_bucket", "retries"} - set(
                dir(job_definition)
            ):
                raise CloudknotInputError(
                    f"job_definition must have attributes {missing_attributes}"
                )
            self._job_definition = job_definition
            self._environment_variables = None

            if environment_variables:
                if not all((isinstance(s, Mapping) for s in environment_variables)):
                    raise CloudknotInputError("env_vars must be a sequence of " "dicts")
                if not all("name" in d and "value" in d for d in environment_variables):
                    raise CloudknotInputError(
                        "each dict in env_vars must " 'have keys "name" and "value"'
                    )
                self._environment_variables = environment_variables

            self._input = input_
            self._array_job = array_job
            self._job_id = self._create()

    @property
    def job_queue_arn(self):
        """ARN for the job queue to which this job will be submitted."""
        return self._job_queue_arn

    @property
    def job_definition(self):
        """
        Job definition on which to base this job.

        Has properties 'name', 'arn', 'output_bucket', and 'retries'
        """
        return self._job_definition

    @property
    def environment_variables(self):
        """Key/value pairs for environment variables sent to the container."""
        return self._environment_variables

    @property
    def input(self):
        """The input to be pickled and sent to the batch job via S3."""
        return self._input

    @property
    def starmap(self):
        """Boolean flag to indicate whether input was 'pre-zipped'."""
        return self._starmap

    @property
    def array_job(self):
        """Boolean flag to indicate whether this is an array job."""
        return self._array_job

    @property
    def job_id(self):
        """The AWS job-ID for this job."""
        return self._job_id

    def _create(self) -> str:  # pragma: nocover
        """
        Create AWS batch job using instance parameters.

        Returns
        -------
        string
            job ID for the created batch job
        """
        # no coverage since actually submitting a batch job for
        # unit testing would be expensive
        bucket = self.job_definition.output_bucket
        sse = get_s3_params().sse
        pickled_input = cloudpickle.dumps(self.input, protocol=DEFAULT_PICKLE_PROTOCOL)

        command = [self.job_definition.output_bucket]
        if self.starmap:
            command = ["--starmap"] + command

        if sse:
            command = ["--sse", sse] + command

        if self.array_job:
            command = ["--arrayjob"] + command

        if self.environment_variables:
            container_overrides = {
                "environment": self.environment_variables,
                "command": command,
            }
        else:
            container_overrides = {"command": command}

        # We have to submit before uploading the input in order to get the
        # jobID first.
        if self.array_job:
            response = clients.batch.submit_job(
                jobName=self.name,
                jobQueue=self.job_queue_arn,
                arrayProperties={"size": len(self.input)},
                jobDefinition=self.job_definition.arn,
                containerOverrides=container_overrides,
            )
        else:
            response = clients.batch.submit_job(
                jobName=self.name,
                jobQueue=self.job_queue_arn,
                jobDefinition=self.job_definition.arn,
                containerOverrides=container_overrides,
            )

        job_id = response["jobId"]
        key = "/".join(
            [
                "cloudknot.jobs",
                self.job_definition.name,
                job_id,
                "input.pickle",
            ]
        )

        # Upload the input pickle
        if sse:
            clients.s3.put_object(
                Bucket=bucket, Body=pickled_input, Key=key, ServerSideEncryption=sse
            )
        else:
            clients.s3.put_object(Bucket=bucket, Body=pickled_input, Key=key)

        # Add this job to the list of jobs in the config file
        self._section_name = self._get_section_name("batch-jobs")
        cloudknot.config.add_resource(self._section_name, job_id, self.name)

        mod_logger.info(
            "Submitted batch job {name:s} with jobID {job_id:s}".format(
                name=self.name, job_id=job_id
            )
        )

        return job_id

    @property
    def status(self) -> dict:
        """
        Query AWS batch job status using instance parameter `self.job_id`.

        Returns
        -------
        status : dict
            Dictionary with keys: {status, statusReason, attempts}
            for this AWS batch job
        """
        if self.clobbered:
            raise ResourceClobberedException(
                "This batch job has already been clobbered.", self.job_id
            )

        self.check_profile_and_region()

        # Query the job_id
        response = clients.batch.describe_jobs(jobs=[self.job_id])
        job = response.get("jobs")[0]

        # Return only a subset of the job dictionary
        keys = ["status", "statusReason", "attempts"]

        if self.array_job:
            keys.append("arrayProperties")

        return {k: job.get(k) for k in keys}  # Return status

    @property
    def log_urls(self) -> list[str]:
        """
        Return the urls of the batch job logs on AWS Cloudwatch.

        Returns
        -------
        log_urls : list
            A list of log urls for each attempt number. If the job has
            not yet run, this will return an empty list
        """
        attempts = sorted(self.status["attempts"], key=lambda a: a["startedAt"])

        log_stream_names = [a["container"].get("logStreamName") for a in attempts]

        def log_name2url(log_name):
            return (
                "https://console.aws.amazon.com/cloudwatch/home?region="
                "{region:s}#logEventViewer:group=/aws/batch/job;"
                "stream={log_name:s}".format(region=self.region, log_name=log_name)
            )

        return [log_name2url(log) for log in log_stream_names]

    @property
    def done(self) -> bool:
        """Return True if the job is done.

        In this case, "done" means the job status is SUCCEEDED or that it is
        FAILED and the job has exceeded the max number of retry attempts
        """
        stat = self.status
        return stat["status"] == "SUCCEEDED" or (
            stat["status"] == "FAILED"
            and len(stat["attempts"]) >= self.job_definition.retries
        )

    def _collect_array_job_result(self, idx: int = 0) -> Any:
        """Collect the array job results and return as a complete list.

        Parameters
        ----------
        idx : int
            Index of the array job element to be retrieved.
            Default: 0

        Returns
        -------
        The array job element at index `idx`
        """
        bucket = self.job_definition.output_bucket

        # For array jobs, different child jobs may have had different
        # numbers of attempts. So we start at the highest possible attempt
        # number and retrieve the latest one.
        attempt = self.job_definition.retries
        result_retrieved = False
        key = None

        while not result_retrieved and attempt >= 0:
            key = "/".join(
                [
                    "cloudknot.jobs",
                    self.job_definition.name,
                    self.job_id,
                    str(idx),
                    "{0:03d}".format(attempt),
                    "output.pickle",
                ]
            )

            try:
                response = clients.s3.get_object(Bucket=bucket, Key=key)
                return pickle.loads(response.get("Body").read())
            except clients.s3.exceptions.NoSuchKey:
                attempt -= 1

        raise CKTimeoutError(
            "Result not available in bucket {bucket:s} with key {key:s}" "".format(
                bucket=bucket, key=key
            )
        )

    def result(self, timeout: Optional[int | float] = None) -> Any:
        """
        Return the result of the latest attempt.

        If the call hasn't yet completed then this method will wait up to
        timeout seconds. If the call hasn't completed in timeout seconds,
        then a CKTimeoutError is raised. If the batch job is in FAILED status
        then a BatchJobFailedError is raised.

        Parameters
        ----------
        timeout: int or float
            timeout time in seconds. If timeout is not specified or None,
            there is no limit to the wait time.
            Default: None

        Returns
        -------
        result:
            The result of the AWS Batch job
        """
        # Set start time for timeout period
        start_time = time.time()

        def time_diff():
            return int(time.time() - start_time)

        while not self.done and (timeout is None or time_diff() < timeout):
            time.sleep(5)

        if not self.done:
            raise CKTimeoutError(self.job_id)

        status = self.status
        if status["status"] == "FAILED":
            raise BatchJobFailedError(self.job_id)
        if self.array_job:
            return [
                self._collect_array_job_result(idx) for idx in range(len(self.input))
            ]
        return self._collect_array_job_result()

    def terminate(self, reason: str):
        """
        Terminate AWS batch job using instance parameter `self.job_id`.

        terminate() combines the cancel and terminate AWS CLI commands. Jobs that
        are in the SUBMITTED, PENDING, or RUNNABLE state must be cancelled,
        while jobs that are in the STARTING or RUNNING state must be terminated.

        Parameters
        ----------
        reason : str
            A message to attach to the job that explains the reason for
            cancelling/terminating it. This message is returned by future
            DescribeJobs operations on the job. This message is also recorded
            in the AWS Batch activity logs.
        """
        if self.clobbered:
            raise ResourceClobberedException(
                "This batch job has already been clobbered.", self.job_id
            )

        self.check_profile_and_region()

        # Require the user to supply a reason for job termination
        if not isinstance(reason, str):
            raise CloudknotInputError("reason must be a string.")

        state = self.status["status"]

        if state in {"SUBMITTED", "PENDING", "RUNNABLE"}:
            clients.batch.cancel_job(jobId=self.job_id, reason=reason)
            mod_logger.info(
                "Cancelled job {name:s} with jobID {job_id:s}".format(
                    name=self.name, job_id=self.job_id
                )
            )
        elif state in {"STARTING", "RUNNING"}:
            clients.batch.terminate_job(jobId=self.job_id, reason=reason)
            mod_logger.info(
                "Terminated job {name:s} with jobID {job_id:s}".format(
                    name=self.name, job_id=self.job_id
                )
            )

    def clobber(self):
        """Kill a batch job and remove its info from config."""
        if self.clobbered:
            return

        self.check_profile_and_region()

        self.terminate(reason="Cloudknot job killed after calling BatchJob.clobber()")

        # Set the clobbered parameter to True,
        # preventing subsequent method calls
        self._clobbered = True

        # Remove this job from the list of jobs in the config file
        cloudknot.config.remove_resource(self._section_name, self.job_id)
