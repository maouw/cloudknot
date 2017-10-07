from __future__ import absolute_import, division, print_function

import inspect
import logging
import operator

from . import aws
from . import config
from .config import CONFIG
from .due import due, Doi

__all__ = ["CloudKnot", "Pars", "Jars"]

# Use duecredit (duecredit.org) to provide a citation to relevant work to
# be cited. This does nothing, unless the user has duecredit installed,
# And calls this with duecredit (as in `python -m duecredit script.py`):
due.cite(Doi(""),
         description="",
         tags=[""],
         path='cloudknot')


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CloudKnot(object):
    def __init__(self, func, source_file):
        if not (func or source_file):
            raise ValueError('you must supply either a user-defined function '
                             'or a source file')
        self.function = func
        self.source_file = source_file

    function = property(operator.attrgetter('_function'))

    @function.setter
    def function(self, f):
        if f:
            if not inspect.isfunction(f):
                raise ValueError('if provided, function must be a '
                                 'user-defined function')
            self._function = f
        else:
            self._function = None

    source_file = property(operator.attrgetter('_source_file'))

    @source_file.setter
    def source_file(self, fileobj):
        if fileobj:
            self._source_file = fileobj
        else:
            self._source_file = None


class Pars(object):
    """PARS stands for Persistent AWS Resource Set

    This object collects AWS resources that could, in theory, be created only
    once for each cloudknot user and used for all of their subsequent AWS
    batch jobs. This set consists of IAM roles, a VPC with subnets for each
    availability zone, and a security group.
    """
    def __init__(self, name='default', batch_service_role_name=None,
                 ecs_instance_role_name=None, spot_fleet_role_name=None,
                 vpc_id=None, vpc_name=None,
                 security_group_id=None, security_group_name=None):
        """Initialize a PARS instance.

        Parameters
        ----------
        name : string
            The name of this PARS. If `pars name` exists in the config file,
            Pars will retrieve those PARS resource parameters. Otherwise,
            Pars will create a new PARS with this name.
            Default: 'default'

        batch_service_role_name : string
            Name of this PARS' batch service IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-batch-service-role'

        ecs_instance_role_name : string
            Name of this PARS' ECS instance IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-ecs-instance-role'

        spot_fleet_role_name : string
            Name of this PARS' spot fleet IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-spot-fleet-role'

        vpc_id : string
            The VPC-ID of the pre-existing VPC that this PARS should adopt
            Default: None

        vpc_name : string
            The name of the VPC that this PARS should create
            Default: name + '-cloudknot-vpc'

        security_group_id : string
            The ID of the pre-existing security group that this PARS should
            adopt
            Default: None

        security_group_name : string
            The name of the security group that this PARS should create
            Default: name + '-cloudknot-security-group'
        """
        # Validate name input
        if not isinstance(name, str):
            raise ValueError('name must be a string')

        self._name = name

        # Validate vpc_name input
        if vpc_name:
            if not isinstance(vpc_name, str):
                raise ValueError('if provided, vpc_name must be a string.')
        else:
            vpc_name = name + '-cloudknot-vpc'

        # Validate security_group_name input
        if security_group_name:
            if not isinstance(security_group_name, str):
                raise ValueError('if provided, security_group_name must be '
                                 'a string.')
        else:
            security_group_name = name + '-cloudknot-security-group'

        # Check for existence of this pars in the config file
        CONFIG.clear()
        CONFIG.read(config.get_config_file())
        self._pars_name = 'pars ' + name
        if self._pars_name in CONFIG.sections():
            # Pars exists, check that user did not provide any resource names
            if any([batch_service_role_name, ecs_instance_role_name,
                    spot_fleet_role_name, vpc_id, security_group_id]):
                raise ValueError('You provided resources for a pars that '
                                 'already exists in configuration file '
                                 '{fn:s}.'.format(fn=config.get_config_file()))

            logging.info('Found PARS {name:s} in config'.format(name=name))
            role_name = CONFIG.get(self._pars_name, 'batch-service-role')
            try:
                # Use config values to adopt role if it exists already
                self._batch_service_role = aws.iam.IamRole(name=role_name)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._batch_service_role = aws.iam.IamRole(
                    name=role_name,
                    description='This AWS batch service role was '
                                'automatically generated by cloudknot.',
                    service='batch',
                    policies=('AWSBatchServiceRole',),
                    add_instance_profile=False
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            role_name = CONFIG.get(self._pars_name, 'ecs-instance-role')
            try:
                # Use config values to adopt role if it exists already
                self._ecs_instance_role = aws.iam.IamRole(name=role_name)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._ecs_instance_role = aws.iam.IamRole(
                    name=role_name,
                    description='This AWS ECS instance role was automatically '
                                'generated by cloudknot.',
                    service='ec2',
                    policies=('AmazonEC2ContainerServiceforEC2Role',),
                    add_instance_profile=True
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            role_name = CONFIG.get(self._pars_name, 'spot-fleet-role')
            try:
                # Use config values to adopt role if it exists already
                self._spot_fleet_role = aws.iam.IamRole(name=role_name)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._spot_fleet_role = aws.iam.IamRole(
                    name=role_name,
                    description='This AWS spot fleet role was automatically '
                                'generated by cloudknot.',
                    service='spotfleet',
                    policies=('AmazonEC2SpotFleetRole',),
                    add_instance_profile=False
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            try:
                # Use config values to adopt VPC if it exists already
                id = CONFIG.get(self._pars_name, 'vpc')
                self._vpc = aws.ec2.Vpc(vpc_id=id)
                logging.info('PARS {name:s} adopted VPC {id:s}'.format(
                    name=name, id=id
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new VPC
                self._vpc = aws.ec2.Vpc(name=vpc_name)
                CONFIG.set(self._pars_name, 'vpc', self.vpc.vpc_id)
                logging.info('PARS {name:s} created VPC {id:s}'.format(
                    name=name, id=self.vpc.vpc_id
                ))

            try:
                # Use config values to adopt security group if it exists
                id = CONFIG.get(self._pars_name, 'security-group')
                self._security_group = aws.ec2.SecurityGroup(
                    security_group_id=id
                )
                logging.info(
                    'PARS {name:s} adopted security group {id:s}'.format(
                        name=name, id=id
                    )
                )
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new security group
                self._security_group = aws.ec2.SecurityGroup(
                    name=security_group_name,
                    vpc=self._vpc
                )
                CONFIG.set(
                    self._pars_name,
                    'security-group', self.security_group.security_group_id
                )
                logging.info(
                    'PARS {name:s} created security group {id:s}'.format(
                        name=name, id=self.security_group.security_group_id
                    )
                )

            # Save config to file
            with open(config.get_config_file(), 'w') as f:
                CONFIG.write(f)
        else:
            # Pars doesn't exist, use input names to adopt/create resources
            # Validate role name input
            if batch_service_role_name:
                if not isinstance(batch_service_role_name, str):
                    raise ValueError('if provided, batch_service_role_name '
                                     'must be a string.')
            else:
                batch_service_role_name = (
                    name + '-cloudknot-batch-service-role'
                )

            try:
                # Create new role
                self._batch_service_role = aws.iam.IamRole(
                    name=batch_service_role_name,
                    description='This AWS batch service role was '
                                'automatically generated by cloudknot.',
                    service='batch',
                    policies=('AWSBatchServiceRole',),
                    add_instance_profile=False
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=batch_service_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._batch_service_role = aws.iam.IamRole(name=e.resource_id)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            # Validate role name input
            if ecs_instance_role_name:
                if not isinstance(ecs_instance_role_name, str):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    raise ValueError('if provided, ecs_instance_role_name '
                                     'must be a string.')
            else:
                ecs_instance_role_name = name + '-cloudknot-ecs-instance-role'

            try:
                # Create new role
                self._ecs_instance_role = aws.iam.IamRole(
                    name=ecs_instance_role_name,
                    description='This AWS ECS instance role was automatically '
                                'generated by cloudknot.',
                    service='ec2',
                    policies=('AmazonEC2ContainerServiceforEC2Role',),
                    add_instance_profile=True
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=ecs_instance_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._ecs_instance_role = aws.iam.IamRole(name=e.resource_id)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            # Validate role name input
            if spot_fleet_role_name:
                if not isinstance(spot_fleet_role_name, str):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    raise ValueError('if provided, spot_fleet_role_name must '
                                     'be a string.')
            else:
                spot_fleet_role_name = name + '-cloudknot-spot-fleet-role'

            try:
                # Create new role
                self._spot_fleet_role = aws.iam.IamRole(
                    name=spot_fleet_role_name,
                    description='This AWS spot fleet role was automatically '
                                'generated by cloudknot.',
                    service='spotfleet',
                    policies=('AmazonEC2SpotFleetRole',),
                    add_instance_profile=False
                )
                logging.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=spot_fleet_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._spot_fleet_role = aws.iam.IamRole(name=e.resource_id)
                logging.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            if vpc_id:
                # Validate vpc_id input
                if not isinstance(vpc_id, str):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    self.spot_fleet_role.clobber()
                    raise ValueError('if provided, vpc_id must be a string')

                # Adopt the VPC
                self._vpc = aws.ec2.Vpc(vpc_id=vpc_id)
                logging.info('PARS {name:s} adopted VPC {id:s}'.format(
                    name=name, id=vpc_id
                ))
            else:
                try:
                    # Create new VPC
                    self._vpc = aws.ec2.Vpc(name=vpc_name)
                    logging.info('PARS {name:s} created VPC {id:s}'.format(
                        name=name, id=self.vpc.vpc_id
                    ))
                except aws.ResourceExistsException as e:
                    # If it already exists, simply adopt it
                    self._vpc = aws.ec2.Vpc(vpc_id=e.resource_id)
                    logging.info('PARS {name:s} adopted VPC {id:s}'.format(
                        name=name, id=e.resource_id
                    ))

            if security_group_id:
                # Validate security_group_id input
                if not isinstance(security_group_id, str):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    self.spot_fleet_role.clobber()
                    self.vpc.clobber()
                    raise ValueError('if provided, security_group_id must '
                                     'be a string')

                # Adopt the security group
                self._security_group = aws.ec2.SecurityGroup(
                    security_group_id=security_group_id
                )
                logging.info(
                    'PARS {name:s} adopted security group {id:s}'.format(
                        name=name, id=security_group_id
                    )
                )
            else:
                try:
                    # Create new security group
                    self._security_group = aws.ec2.SecurityGroup(
                        name=security_group_name,
                        vpc=self.vpc
                    )
                    logging.info(
                        'PARS {name:s} created security group {id:s}'.format(
                            name=name, id=self.security_group.security_group_id
                        )
                    )
                except aws.ResourceExistsException as e:
                    # If it already exists, simply adopt it
                    self._security_group = aws.ec2.SecurityGroup(
                        security_group_id=e.resource_id
                    )
                    logging.info(
                        'PARS {name:s} adopted security group {id:s}'.format(
                            name=name, id=e.resource_id
                        )
                    )

            # Save the new pars resources in config object
            # Use CONFIG.set() for python 2.7 compatibility
            CONFIG.add_section(self._pars_name)
            CONFIG.set(
                self._pars_name,
                'batch-service-role', self._batch_service_role.name
            )
            CONFIG.set(
                self._pars_name,
                'ecs-instance-role', self._ecs_instance_role.name
            )
            CONFIG.set(
                self._pars_name,
                'spot-fleet-role', self._spot_fleet_role.name
            )
            CONFIG.set(
                self._pars_name,
                'vpc', self._vpc.vpc_id
            )
            CONFIG.set(
                self._pars_name,
                'security-group', self._security_group.security_group_id
            )

            # Save config to file
            with open(config.get_config_file(), 'w') as f:
                CONFIG.write(f)

    name = property(fget=operator.attrgetter('_name'))
    pars_name = property(fget=operator.attrgetter('_pars_name'))

    @staticmethod
    def _role_setter(attr):
        """Static method to return setter methods for new IamRoles"""
        def set_role(self, new_role):
            """Setter method to attach new IAM role to this PARS

            This method clobbers the old role and adopts the new one.

            Parameters
            ----------
            new_role :
                new IamRole instance to attach to this Pars

            Returns
            -------
            None
            """
            # Verify input
            if not isinstance(new_role, aws.iam.IamRole):
                raise ValueError('new role must be an instance of IamRole')

            old_role = getattr(self, attr)

            logging.warning(
                'You are setting a new role for PARS {name:s}. The old '
                'role {role_name:s} will be clobbered.'.format(
                    name=self.name, role_name=old_role.name
                )
            )

            # Delete the old role
            old_role.clobber()

            # Set the new role attribute
            setattr(self, attr, new_role)

            # Replace the appropriate line in the config file
            CONFIG.clear()
            CONFIG.read(config.get_config_file())
            field_name = attr.lstrip('_').replace('_', '-')
            CONFIG.set(self._pars_name, field_name, new_role.name)
            with open(config.get_config_file(), 'w') as f:
                CONFIG.write(f)

            logging.info(
                'PARS {name:s} adopted new role {role_name:s}'.format(
                    name=self.name, role_name=new_role.name
                )
            )

        return set_role

    batch_service_role = property(
        fget=operator.attrgetter('_batch_service_role'),
        fset=_role_setter.__func__('_batch_service_role')
    )
    ecs_instance_role = property(
        fget=operator.attrgetter('_ecs_instance_role'),
        fset=_role_setter.__func__('_ecs_instance_role')
    )
    spot_fleet_role = property(
        fget=operator.attrgetter('_spot_fleet_role'),
        fset=_role_setter.__func__('_spot_fleet_role')
    )

    vpc = property(operator.attrgetter('_vpc'))

    @vpc.setter
    def vpc(self, v):
        """Setter method to attach new VPC to this PARS

        This method clobbers the old VPC and adopts the new one.

        Parameters
        ----------
        v : Vpc
            new Vpc instance to attach to this Pars

        Returns
        -------
        None
        """
        if not isinstance(v, aws.ec2.Vpc):
            raise ValueError('new vpc must be an instance of Vpc')

        logging.warning(
            'You are setting a new VPC for PARS {name:s}. The old '
            'VPC {vpc_id:s} will be clobbered.'.format(
                name=self.name, vpc_id=self.vpc.vpc_id
            )
        )

        # We have to replace the security group too, since it depends on the
        # VPC. Create a new security group based on the new VPC but with the
        # old name and description.
        sg_name = self.security_group.name
        sg_desc = self.security_group.description

        # The security group setter method will take care of clobbering the
        # old security group and updating config, etc.
        self.security_group = aws.ec2.SecurityGroup(
            name=sg_name, vpc=v, description=sg_desc
        )

        self._vpc.clobber()
        self._vpc = v

        # Replace the appropriate line in the config file
        CONFIG.clear()
        CONFIG.read(config.get_config_file())
        CONFIG.set(self._pars_name, 'vpc', v.vpc_id)
        with open(config.get_config_file(), 'w') as f:
            CONFIG.write(f)

        logging.info(
            'PARS {name:s} adopted new VPC {id:s}'.format(
                name=self.name, id=self.vpc.vpc_id
            )
        )

    security_group = property(operator.attrgetter('_security_group'))

    @security_group.setter
    def security_group(self, sg):
        """Setter method to attach new security group to this PARS

        This method clobbers the old security group and adopts the new one.

        Parameters
        ----------
        sg : SecurityGroup
            new SecurityGroup instance to attach to this Pars

        Returns
        -------
        None
        """
        if not isinstance(sg, aws.ec2.SecurityGroup):
            raise ValueError('new security group must be an instance of '
                             'SecurityGroup')

        logging.warning(
            'You are setting a new security group for PARS {name:s}. The old '
            'security group {sg_id:s} will be clobbered.'.format(
                name=self.name, sg_id=self.security_group.security_group_id
            )
        )
        old_sg = self._security_group
        old_sg.clobber()
        self._security_group = sg

        # Replace the appropriate line in the config file
        CONFIG.clear()
        CONFIG.read(config.get_config_file())
        CONFIG.set(self._pars_name, 'security-group', sg.security_group_id)
        with open(config.get_config_file(), 'w') as f:
            CONFIG.write(f)

        logging.info(
            'PARS {name:s} adopted new security group {id:s}'.format(
                name=self.name, id=sg.security_group_id
            )
        )

    def clobber(self):
        """Delete associated AWS resources and remove section from config

        Returns
        -------
        None
        """
        # Delete all associated AWS resources
        self._security_group.clobber()
        self._vpc.clobber()
        self._spot_fleet_role.clobber()
        self._ecs_instance_role.clobber()
        self._batch_service_role.clobber()

        # Remove this section from the config file
        CONFIG.clear()
        CONFIG.read(config.get_config_file())
        CONFIG.remove_section(self._pars_name)
        with open(config.get_config_file(), 'w') as f:
            CONFIG.write(f)

        logging.info('Clobbered PARS {name:s}'.format(name=self.name))


class Jars(object):
    def __init__(self, name='default', pars=None,
                 docker_image_name='cloudknot-docker-image',
                 job_definition_name='cloudknot-job-definition',
                 compute_environment_name='cloudknot-compute-environment',
                 job_queue_name='cloudknot-job-queue', vcpus=1, memory=32000):
        # Validate name input
        if not isinstance(name, str):
            raise ValueError('name must be a string')

        self._name = name

        # Validate and set the PARS
        if pars:
            if not isinstance(pars, Pars):
                raise ValueError('infrastructure must be an AWSInfrastructure '
                                 'instance.')
            self._pars = pars
        else:
            self._pars = Pars()

        if not isinstance(docker_image_name, str):
            raise ValueError('docker_image_name must be a string.')

        if not isinstance(job_definition_name, str):
            raise ValueError('job_definition_name must be a string.')

        if not isinstance(compute_environment_name, str):
            raise ValueError('compute_environment_name must be a string.')

        if not isinstance(job_queue_name, str):
            raise ValueError('job_queue_name must be a string.')

        try:
            cpus = int(vcpus)
            if cpus < 1:
                raise ValueError('vcpus must be positive')
        except ValueError:
            raise ValueError('vcpus must be an integer')

        try:
            mem = int(memory)
            if mem < 1:
                raise ValueError('memory must be positive')
        except ValueError:
            raise ValueError('memory must be an integer')

        # WIP
        # self._docker_image = aws.ecr.DockerImage(
        #     func=func,
        #     script_path=,
        #     dir_name=,
        #     username=
        # )

        # self._docker_repo = aws.ecr.DockerRepo(
        #     name=docker_repo_name,
        # )

        self._job_definition = aws.batch.JobDefinition(
            name=job_definition_name,
            job_role=self._infrastructure.ecs_instance_role,
            docker_image=self._docker_image.uri,
            vcpus=cpus,
            memory=mem,
            username=username,
            retries=retries
        )

        self._compute_environment = aws.batch.ComputeEnvironment(
            name=compute_environment_name,
            batch_service_role=self._pars.batch_service_role,
            instance_role=self._pars.ecs_instance_role,
            vpc=self._pars.vpc,
            security_group=self._pars.security_group,
            spot_fleet_role=self._pars.spot_fleet_role,
            instance_types=instance_types,
            resource_type=resource_type,
            min_vcpus=min_vcpus,
            max_vpucs=max_vcpus,
            desired_vcpus=desired_vcpus,
            image_id=image_id,
            ec2_key_pair=key_pair,
            tags=ce_tags,
            bid_percentage=bid_percentage
        )

        self._job_queue = aws.batch.JobQueue(
            name=job_queue_name,
            compute_environments=self._compute_environment,
            priority=priority
        )

    pars = property(operator.attrgetter('_pars'))
    docker_image = property(operator.attrgetter('_docker_image'))
    docker_repo = property(operator.attrgetter('_docker_repo'))
    job_definition = property(operator.attrgetter('_job_definition'))
    job_queue = property(operator.attrgetter('_job_queue'))
    compute_environment = property(operator.attrgetter('_compute_environment'))
