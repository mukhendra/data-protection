#######################################################################
#                                                                     #
#   Create a subordinate private certificate authority(CA) using ACM  #
#                                                                     #
#######################################################################

import boto3
import os
import sys 
import random
import pytz
import json
import subprocess

try:
    az = subprocess.check_output(['curl','-s','http://169.254.169.254/latest/meta-data/placement/availability-zone'])
    list_az = az.split('-')
    region = list_az[0]+'-'+list_az[1]+'-'+list_az[2][0]   
    acm_pca_client = boto3.client('acm-pca',region_name=region)
    s3_client = boto3.client('s3',region_name=region)
    ddb_client = boto3.client('dynamodb',region)

    subordinate_ca_serial_number = random.randint(1, 100000)
    common_name = 'reinvent.builder.subordinate'
    
    subject = {
        'Country': 'US',
        'Organization': 'customer',
        'OrganizationalUnit': 'customerdept',
        'State': 'Nevada',
        'CommonName': common_name,
        'SerialNumber': unicode(str(subordinate_ca_serial_number)),
        'Locality': 'Las Vegas'
    }

    dbg = 'Stop'  
    ####################################################################
    #                                                                  #
    #   Creating the subject for the private certificate authority     #
    #                                                                  #
    ####################################################################
  
    crl_bucket_name = 'reinvent-builder-bucket-pca-crl' + str(random.randint(1, 100000))
    s3_client.create_bucket(Bucket=crl_bucket_name)
   
    response = s3_client.put_bucket_tagging(
        Bucket=crl_bucket_name,
        Tagging={
            'TagSet': [
                {
                    'Key': 'reinvent',
                    'Value': 'dataencryption_builderssession'
                },
            ]
        }
    )
    
    dbg = 'Stop'            
    #################################################################################
    #                                                                               #
    #   Create an S3 bucket for storing certificate revocation lists(crl)           #
    #                                                                               #
    #   Also tag the bucket so that it can be associated with this builders session #
    #   for cleanup                                                                 #
    #                                                                               #
    #################################################################################
   
    current_directory_path = os.path.dirname(os.path.realpath(__file__)) + '/'
    crl_s3_bucket_policy_json = current_directory_path + 'crl_bucket_policy.json'

    crl_bucket_policy = json.loads(open(crl_s3_bucket_policy_json, 'rb').read())
    crl_bucket_policy['Statement'][0]['Resource'][0] = unicode("arn:aws:s3:::"+crl_bucket_name+"/*", 'utf_8')
    crl_bucket_policy['Statement'][0]['Resource'][1] = unicode("arn:aws:s3:::"+crl_bucket_name, 'utf_8')
    
    # Set bucket policy CRL S3 bucket
    response = s3_client.put_bucket_policy(
                Bucket=crl_bucket_name,
                Policy=json.dumps(crl_bucket_policy)
                )
    
    dbg = 'Stop'            
    #################################################################################
    #                                                                               #
    #   ACM service should be able to write/update crl to this S3 bucket            #
    #   therefore we need to put a bucket policy which gives permission to ACM      #
    #                                                                               #
    #   The bucket policy is stored in this file called crl_bucket_policy.json      #
    #                                                                               #
    #################################################################################
    
    response = acm_pca_client.create_certificate_authority(
        CertificateAuthorityConfiguration={
            'KeyAlgorithm': 'RSA_2048',
            'SigningAlgorithm': 'SHA256WITHRSA',
            'Subject': subject
        },
        RevocationConfiguration={
            'CrlConfiguration': {
                'Enabled': True,
                'ExpirationInDays': 20,
                'S3BucketName': crl_bucket_name
            }
        },
        CertificateAuthorityType='SUBORDINATE',
        IdempotencyToken='reinvent-builder-subordinate'
    )
    
    dbg = 'Stop'            
    #######################################################################################
    #                                                                                     #
    #   Creates the subordinate private certificate authority in AWS Certificate Manager  #
    #   the api returns the arn of the private CA that was created                        #
    #                                                                                     #
    #######################################################################################
    
    subordinate_pca_arn = response['CertificateAuthorityArn']
    print "Creating private certificate authority\n"
    
    while True:
        response = acm_pca_client.describe_certificate_authority(
            CertificateAuthorityArn=subordinate_pca_arn
        )
        
        if response['CertificateAuthority']['Status'] == 'PENDING_CERTIFICATE':
            print "\nPrivate CA has been created"
            print "Please generate the CSR and get it signed by your organizations's root cert"
            break
        else:
            print "*"
            continue
        break
        
    print "\nSuccess : The ARN of the subordinate private certificate authority is : \n" + subordinate_pca_arn

    dbg= 'Stop';
    #############################################################################################
    #                                                                                           #
    #   The infinite loop exists to make sure that the subordinate certificate authority        #
    #   creation is complete and the status is PENDING_CERTIFICATE which means the subordinate  #
    #                                                                                           #
    #   CA can now be signed by your organization's root cert                                   #
    #############################################################################################
   
    response = ddb_client.update_item(
        ExpressionAttributeNames={
            '#spa': 'subordinate_pca_arn',
            '#scsn': 'subordinate_ca_serial_number',
        },
        ExpressionAttributeValues={
            ':a': {
                'S': subordinate_pca_arn,
            },
            ':b': {
                'N': str(subordinate_ca_serial_number),
            },
        },
        Key={
            'shared_variables': {
                'N': '1000',
            },
            'session': {
                'N': '1000',
            },
        },
        ReturnValues='ALL_NEW',
        TableName='shared_variables_crypto_builders',
        UpdateExpression='SET #spa = :a, #scsn = :b',
    )
    
    dbg = 'Stop' 
    #########################################################################
    #   Storing variables in dynamoDB so that other python modules to use   #
    #########################################################################
    
except SystemExit as e:
    exit(0)    
except:
    print "Unexpected error:", sys.exc_info()[0]
    raise
else:
    exit(0)
 
