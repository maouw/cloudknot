.. _getting-started-label:

Getting started with cloudknot
==============================

To get started with cloudknot you will need an AWS account with the proper
permisssions and you will need to install cloudknot.


Obtaining an AWS account
------------------------

If you haven't already done so, create an `Amazon Web Services (AWS)
<https://aws.amazon.com>`_ account.


Installation and configuration
------------------------------

You can install cloudknot from PyPI (recommended)::

   pip install cloudknot

or from the `github repository <https://github.com/richford/cloudknot>`_.
This will install cloudknot and its dependencies, including the AWS command
line utilities. If you haven't already done so, we recommend that you follow
the `awscli configuration instructions
<http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html>`_.

If you have a "default" profile listed in either the AWS credentials file or
the AWS CLI configuration file, then cloudknot should work out of the box.
If you don't know what either of those files are, read about
`AWS configuration files
<https://docs.aws.amazon.com/cli/latest/userguide/cli-config-files.html>`_.


Permissions
-----------

To use cloudknot, you must have the same permissions required to use AWS
Batch. You can attach a managed policy, such as `AWSBatchFullAccess
<https://docs.aws.amazon.com/batch/latest/userguide/batch_managed_policies.html>`_
or `AWSBatchUserPolicy
<https://docs.aws.amazon.com/batch/latest/userguide/batch_IAM_user_policies.html>`_.
If you prefer to write your own policies, the minimal permissions required
for a cloudknot user should be contained in the following policy summary:

.. container:: toggle

   .. container:: header

      **policy summary**

   .. container:: content

      .. literalinclude:: minimal_permissions.txt
         :language: none


Using multiple AWS profiles
---------------------------

If you want to use cloudknot with multiple AWS profiles, make sure that you
have the profiles configured in the AWS credentials file, e.g.:

.. literalinclude:: example_credentials.txt
   :language: none

or in the AWS config file, e.g.:

.. literalinclude:: example_config.txt
   :language: none

Then you can use the cloudknot functions :func:`cloudknot.aws.set_profile`,
:func:`cloudknot.aws.get_profile`, and :func:`cloudknot.aws.list_profiles`
to interact with your various AWS profiles.


Region shopping
---------------

You may want to shop the AWS regions for the cheapest spot instance pricing
(see `this page
<http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances-history.html>`_
for details). You can view and change the region in which your cloudknot
resources reside and in which you will launch your AWS Batch jobs by using the
:func:`cloudknot.aws.get_region` and :func:`cloudknot.aws.set_region` functions.


.. _eg-label:

Examples
--------

See the `examples directory
<https://github.com/richford/cloudknot/tree/master/examples>`_ on github for
(you guessed it) examples of how to use cloudknot.


AWS resource limitations
------------------------

AWS places `some limits
<https://docs.aws.amazon.com/general/latest/gr/aws_service_limits.html>`_
on the number of services in each region for an AWS account. The most relevant
limits for cloudknot users are the `AWS Virtual Private Cloud (VPC) limits
<https://docs.aws.amazon.com/general/latest/gr/aws_service_limits.html#limits_vpc>`_,
which limit the number of VPCs per region to five, and the `AWS Batch limits
<https://docs.aws.amazon.com/general/latest/gr/aws_service_limits.html#limits_batch>`_,
which limit the number of compute environments and job queues. For most use
cases, these limits should not be a problem. However, if you are using
cloudknot along with other users in the same organization, you might bump up
against these limitations. To avoid the VPC limit, try always to use the
default VPC or to agree with your coworkers on using an organization-wide
PARS name. To avoid the batch limits, :ref:`clobber <clobber-label>` old knots
that you are no longer using. If none of those approaches work for you, you can
`request increases to some service limits
<https://docs.aws.amazon.com/general/latest/gr/aws_service_limits.html>`_.

If the terms ":ref:`knot <knot-label>`," ":ref:`PARS <pars-label>`," and
":ref:`clobber <clobber-label>`" in the preceding paragraph confound
you, take a look at the :ref:`cloudknot documentation <doc-label>`.


Debugging and logging
---------------------

Cloudknot will print logging info to the console by setting the
`CLOUDKNOT_LOGLEVEL` environment variable::

    CLOUDKNOT_LOGLEVEL=INFO

Cloudknot also writes a much more verbose log for the current session in the
user's home directory in the path returned by

.. code-block:: python

    import os.path as op
    op.join(op.expanduser('~'), '.cloudknot', 'cloudknot.log')