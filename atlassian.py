# -*- coding: utf-8 -*-

import subprocess
import datetime
import sys
import re
import netifaces as ni # sudo pip install netifaces
import socket
import time
import httplib
import xml.etree.ElementTree as ET
import requests
import urllib, json

# Import salt modules
import salt.client
import salt.runner

log_file_location = "/srv/logs/"

def createTestMachine(atlassian_product=""):
    '''
    Creates a test environment for any of the four Atlassian Products
    '''     
    
    atlassian_versions = getCurrentAtlassianProductsVersions()
    prompt = "Please enter the Atlassian Product for which a test machine is being created (Jira, Confluence, Bamboo, Bitbucket): "
    atlassian_product = validateAtlassianProduct(atlassian_product, prompt)
    atlassian_data = getAtlassianData(atlassian_product, atlassian_versions)
    prod_hostname = atlassian_data["prod_hostname"]
    test_hostname = atlassian_data["test_hostname"]
    service = atlassian_data["service"]
    createBashScript(test_hostname, service)
    createCloudProfile(test_hostname, atlassian_data["ip"], prod_hostname, "DevAtlassian")
    createRosterFile(test_hostname)
    
    # Creates the client object, and makes sure that the minion is present
    client = salt.client.LocalClient(__opts__['conf_file'])
    runnerClient = salt.runner.RunnerClient(__opts__)

    error_message = "An error occured, cannot disable services on " + prod_hostname
    disable_prod_services = "states." + service + ".disable-services"
    if not runSaltStateSuccess(prod_hostname, disable_prod_services, error_message, client): 
        return False
    
    print "Cloning machine, this usually takes about five to ten minutes..."

    runnerClient.cmd('cloud.profile', [test_hostname, test_hostname])

    error_message = "An error occured, cannot disable services on " + prod_hostname
    disable_prod_services = "states." + service + ".enable-services"
    if not runSaltStateSuccess(prod_hostname, disable_prod_services, error_message, client): 
        return False

    error_message = "An error occured, cannot change salt masters on " + test_hostname
    change_salt_master = "states." + service + ".configure-test-machine"
    if not runSaltStateSuccess("SaltMasterProd", change_salt_master, error_message, client): 
        return False
    
    return True

def verifyTestMachine(atlassian_product=""):
    '''
    Verifies that the test machine is ready to go, and will start the atlassian service.
    '''
    client = salt.client.LocalClient(__opts__['conf_file'])
    atlassian_versions = getCurrentAtlassianProductsVersions()
    prompt = "Please which atlassian test machine is being checked (Jira, Confluence, Bamboo, Bitbucket): "
    atlassian_product = validateAtlassianProduct(atlassian_product, prompt)
    atlassian_data = getAtlassianData(atlassian_product, atlassian_versions)

    error_message = "An error occured, test machine configs are not ready on " + atlassian_data["test_hostname"]
    check_test_machine = "states." + atlassian_data["service"] + ".check-test-machine"
    if not runSaltStateSuccess(atlassian_data["test_hostname"], check_test_machine, error_message, client): 
        return False
    
    return True

def runUpgrade(hostname="", version_upgrading_to = ""):
    '''
    Runs and Atlassian Upgrade on either prod or test machines based on what master you run it on
    '''
    
    

    runnerClient = salt.runner.RunnerClient(__opts__)
    enviornment = ""
    localMinion = socket.gethostname().split('.')[0]
    if localMinion == 'SaltMasterProd':
        enviornment = "prod"
        print "Upgrading a Production Machine"
        if not verifyIfProd():
            return False
    else:
        enviornment = "test"
        print "Upgrading a Test Machine"

    while True:
        if enviornment == "prod":
            if hostname not in ["Confluence", "JIRA2016", "MTCBamboo", "MTCStash"]:
                hostname = raw_input("We are upgrading production. Please enter one of the hostnames for one of the production machines. (Confluence, JIRA2016, MTCBamboo, MTCStash): ")
            else:
                print "Upgrading the production machine with " + hostname + " as the hostname."
                break
        elif enviornment == "test":
            if hostname not in ["ConfluenceTest", "JiraTest", "BambooTest", "BitbucketTest"]:
                hostname = raw_input("We are upgrading test. Please enter one of the hostnames for one of the test machiens. (ConfluenceTest, JiraTest, BambooTest, BitbucketTest): ")
            else:
                print "Upgrading the test machine with " + hostname + " as the hostname."
                break
        else:
            print "Hostname: " + hostname + " is invalid. Please try again"
    
    all_atlassian_versions = getCurrentAtlassianProductsVersions()
    atlassian_product = getAtlassianProductFromHostname(hostname)
    data = getAtlassianData(atlassian_product, all_atlassian_versions)

    #Finds out what version, if any, should be tested
    version_upgrading_to = checkAtlassianVersion(data, version_upgrading_to)

    while True:
        confirm = raw_input("Upgrading " + atlassian_product + " from " + data['current_version'] + " to version " + version_upgrading_to + " on " + hostname + ". Confirm? (y/n): ")
        if confirm == "y" or confirm == "yes":
            print "Proceding with the upgrade"
            break
        elif confirm == "n" or confirm == "no":
            print "Cancelling Upgrade"
            return False
        else:
            print "That was neither y, yes, n, or no. Let's try again"
    
    if hostname in ["MTCStash", "BitbucketTest"]:
        pillars = {
            "version_updating_to" : version_upgrading_to, 
            "current_version" : data['current_version'],
            "target" : hostname
        }
    else:
        pillars = {
            "version_updating_to" : version_upgrading_to, 
            "target" : hostname
        }
    
    # Create Output Log File
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M") 
    output_filename = log_file_location + "atlassian_upgrade_" + data["service"] + "_" + date + ".log"
    output = open(output_filename, "w+")

    result = runnerClient.cmd('state.orchestrate', ['orchs.update_' + data["service"], 'base', None, None, pillars])
    output.write(result)
    output.close()
    return True
    
        
        
    

# Helper Functions *******************************************************************************************************
VCENTER_PROVIDER = "my-vmware-config"


networkInterfaces = {
        '10.0.33'   :  ('10.0.33.1', 'dvVLAN918 10.0.33.0 25 (1)'),
        '10.1.16'   :  ('10.1.16.1', 'dvVLAN118 10.1.16.x (1)'),
        '10.5.16'   :  ('10.5.16.1', 'dvVLAN518 10.5.16.0 (1)'),
        '10.8.16'   :  ('10.8.16.1', 'dvVLAN818 10.8.16.0 (1)'),
        '10.8.17'   :  ('10.8.17.1', 'dvVLAN891 10.8.17.64 28 (1)'),
        '10.8.20'   :  ('10.8.20.129', 'dvVLAN850 10.8.20.128 25 (1)'),
        '10.8.21'   :  ('10.8.21.1', 'dvVLAN810 10.8.21.0 24 DBZonE (1)'),
        '10.8.22'   :  ('10.8.22.1', 'dvVLAN825 10.8.22.0 (1)'),        
        '10.8.23'   :  ('10.8.23.1', 'dvVLAN811 10.8.23.0 24 AppZone (1)'),
        '10.8.29'   :  ('10.8.29.1', 'dvVLAN996DMZ 10.8.29.16 (1)'),
        '172.16.0'  :  ('172.16.0.1', 'dvVlan150-vMotion 172.16.0.0 (1)'),
        '172.16.4'  :  ('172.16.4.1', 'dvVlan170-vSAN 172.16.4.0 (1)'),
        '172.16.5'  :  ('172.16.5.1', 'dvVlan180-ContainerBridge 172.16.5.0 (1)')
    }


def verifyIfProd():
    making_sure = raw_input("You have selected production. Are you sure? (y/n): ")
    if making_sure == "y" or making_sure == "yes":
        print "Upgrading Production"
        return True
    elif making_sure == "n" or making_sure == "no":
        print "Good thing we double checked."
        return False
    else:
        print "That was neither yes or no. Let's try again"
        return False

def getAtlassianProductFromHostname(hostname):
    while True:
        if hostname == "Confluence" or hostname == "ConfluenceTest":
            atlassian_product = "Confluence"
            return atlassian_product
        elif hostname == "MTCStash" or hostname == "BitbucketTest":
            atlassian_product = "Bitbucket"
            return atlassian_product
        elif hostname == "MTCBamboo" or hostname == "BambooTest":
            atlassian_product = "Bamboo"
            return atlassian_product
        elif hostname == "JIRA2016" or hostname == "JiraTest":
            atlassian_product = "Jira"
            return atlassian_product
        else:
            hostname = raw_input("Invalid hostname entered. Please enter one of the following hostnames:\nConfluence, ConfluenceTest, MTCStash, BitbucketTest, MTCBamboo, BambooTest, JIRA2016, JiraTest: ")
    

def validateAtlassianProduct(atlassian_product, prompt):
    while True:
        if atlassian_product == "":
            atlassian_product = raw_input(prompt)

        if atlassian_product not in ['Bamboo', 'Bitbucket', 'Jira', 'Confluence']:
            print (atlassian_product + " is invalid, please enter either Jira, Confluence, Bamboo, or Bitbucket")
            atlassian_product = ""
        else:
            break
    return atlassian_product

def checkAtlassianVersion(data, version_updating_to):
    '''
    Checks if the Atlassian Version is valid
    '''
    if version_updating_to == "":
        version_updating_to = raw_input("What version of " + data["service"] + " would you like to test?: ")
    while True:
        if versiontuple(version_updating_to) > versiontuple(data["current_version"]):
            url = data["url"] + version_updating_to + data["extention"]
            request = requests.get(url)
            if request.status_code == 200:
                return version_updating_to
            else:
                version_updating_to = raw_input(version_updating_to + " does not exists. Please enter a valid version greater than " + data["current_version"] + ": ")
        else:
            version_updating_to = raw_input(version_updating_to + " is equal to or less than the current version of " + data["service"] + ". Please enter a valid version greater than " + data["current_version"] + ": ")
    
def getCurrentAtlassianProductsVersions():
    '''
    Gets the current version for all the atlassian products
    '''
    runnerClient = salt.runner.RunnerClient(__opts__)
    pillars = runnerClient.cmd('pillar.show_pillar', print_event=False)
    BAMBOO_PASSWORD = pillars['some_secret_password']
    BAMBOO_USERNAME = 'User'
    BITBUCKET_USERNAME = 'User'
    BITBUCKET_PASSWORD = pillars['some_secret_password']

    atlassian_versions = {
        "Confluence":"",
        "Bamboo":"",
        "Jira":"",
        "Bitbucket":""
    }

    confluence_version = parseXMLRequestForVersionNumber("https://kb.mtc.byu.edu/rest/applinks/1.0/manifest", BAMBOO_USERNAME, BAMBOO_PASSWORD)
    atlassian_versions["Confluence"] = confluence_version

    bamboo_version = parseXMLRequestForVersionNumber("https://bamboo.mtc.byu.edu/rest/api/latest/info", BAMBOO_USERNAME, BAMBOO_PASSWORD)
    atlassian_versions["Bamboo"] = bamboo_version

    jira_version = parseJSONRequestForVersionNumber("https://jira.mtc.byu.edu/jira/rest/api/2/serverInfo", BAMBOO_USERNAME, BAMBOO_PASSWORD)
    atlassian_versions["Jira"] = jira_version

    bitbucket_version = parseJSONRequestForVersionNumber('https://bitbucket.mtc.byu.edu/rest/api/1.0/application-properties', BITBUCKET_USERNAME, BITBUCKET_PASSWORD)
    atlassian_versions['Bitbucket'] = bitbucket_version

    return atlassian_versions


def parseXMLRequestForVersionNumber(url, username, password):
    '''
    Parses and XML to get the version number
    '''
    req = requests.get(url, stream=True, verify=False, auth=(username, password))
    data = req.content
    tree = ET.ElementTree(ET.fromstring(data))
    root = tree.getroot()
    version = root.find("version").text
    return version


def parseJSONRequestForVersionNumber(url, username, password):
    '''
    Parses a JSON to get the version number and return the number
    '''
    req = requests.get(url, stream=True, verify=False, auth=(username, password))
    response = req.json()
    version = response["version"]
    return version

def createBashScript(hostname, service):
    '''
    Creates a bash script that will be run when a test machine is created
    '''
    confFile = open("/etc/salt/cloud.deploy.d/" + hostname + ".sh", "w+")
    confFile.write("sudo mv -f /etc/salt/minion.d/" + service + "-beacon.conf /tmp/\n")
    confFile.write("sudo yum -y remove salt-minion\n")
    confFile.write("sudo rm -rf /etc/salt\n")
    confFile.write("sudo yum -y install salt-minion\n")
    confFile.write("sudo sed -i -e 's/#master: salt/master: 10.8.16.70/g' /etc/salt/minion\n")
    confFile.write("sudo sed -i -e 's/#id:/id: " + hostname + "/g' /etc/salt/minion\n")
    confFile.write("sudo mv -f /tmp/" + service + "-beacon.conf /etc/salt/minion.d/\n")
    if hostname == "ConfluenceTest":
        confFile.write("sh /opt/dynatrace/oneagent/agent/uninstall.sh\n")
    confFile.close()

def createRosterFile(hostname):
    '''
    Creates a roster file to be used to run salt-ssh commands
    '''
    confFile = open("/etc/salt/roster.d/atlassian-test-" + hostname, "w+")
    confFile.write("test-env:\n")
    confFile.write("  host: " + hostname + "\n")
    confFile.write("  user: DevOps\n")
    confFile.write("  sudo: True\n")
    confFile.write("\n")
    confFile.write("master-dev:\n")
    confFile.write("  host: SaltMasterDev\n")
    confFile.write("  user: DevOps\n")
    confFile.write("  sudo: True\n")
    confFile.close()

def createCloudProfile(hostname, ip, cloneFrom, folder='none'):
    '''
    Creates a profile to make changes to the cloned VM
    '''
    runnerClient = salt.runner.RunnerClient(__opts__)
    pillars = runnerClient.cmd('pillar.show_pillar', print_event=False)
    ROOT_PASSWORD = pillars['some_secret_password'] # SSH keys is another option
    runnerClient = salt.runner.RunnerClient(__opts__)
    
    valid_ip = re.search('\A\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', ip).group(0)
    
    if not valid_ip:
        print (ip + " is an invalid IP Address!")
        return False
    
    subnet = re.search('\A\d{1,3}\.\d{1,3}\.\d{1,3}', ip).group(0)
    
    # Uses the network interfaces dict above to find the correct gateway and subnet
    gateway = (networkInterfaces[subnet])[0]
    networkInterface = networkInterfaces[subnet][1]

    # Builds the conf profile for confluence
    confFile = open("/etc/salt/cloud.profiles.d/" + hostname + ".conf", "w+")
    confFile.write(hostname + ":\n")
    confFile.write("   provider: " + VCENTER_PROVIDER + "\n")
    confFile.write("   clonefrom: " + cloneFrom + "\n")
    confFile.write("   password: " + ROOT_PASSWORD + "\n")
    confFile.write("   devices:\n")
    confFile.write("      network:\n")
    confFile.write("         Network adapter 1:\n")
    confFile.write("            name: " + networkInterface + "\n")
    confFile.write("            switch_type: distributed\n")
    confFile.write("            ip: " + ip + "\n")
    confFile.write("            gateway: [" + gateway + "]\n")
    confFile.write("            subnet_mask: 255.255.255.0\n")
    confFile.write("            domain: mtc.byu.edu\n")
    confFile.write("   domain: mtc.byu.edu\n")
    confFile.write("   ssh_username: DevOps\n")
    confFile.write("   dns_servers:\n")
    confFile.write("      - 10.8.16.99\n")
    confFile.write("      - 10.8.16.185\n")
    confFile.write("   resourcepool: Production\n")
    confFile.write("   folder: " + folder + "\n")    
    confFile.write("   script: " + hostname + "\n")
    
    confFile.close()

    return gateway

def getAtlassianData(atlassian_product, versions):
    '''
    Holds the data for the different atlassian versions
    '''
    data = {
        "prod_hostname" : "",
        "test_hostname" : "",
        "url" : "",
        "extention" : "",
        "current_version" : versions[atlassian_product],
        "service" : "",
        "ip" : ""
    }
    if atlassian_product == "Jira":
        data["prod_hostname"] = "JIRA2016"
        data["test_hostname"] = "JiraTest"
        data["url"] = "http://www.atlassian.com/software/jira/downloads/binary/atlassian-jira-software-"
        data["extention"] = "-x64.bin"
        data["service"] = "jira"
        data["ip"] = "10.8.16.191"

    elif atlassian_product == "Bamboo":
        data["prod_hostname"] = "MTCBamboo"
        data["test_hostname"] = "BambooTest"
        data["url"] = "https://www.atlassian.com/software/bamboo/downloads/binary/atlassian-bamboo-"
        data["extention"] = ".tar.gz"
        data["service"] = "bamboo"
        data["ip"] = "10.8.16.136"

    elif atlassian_product == "Bitbucket":
        data["prod_hostname"] = "MTCStash"
        data["test_hostname"] = "BitbucketTest"
        data["url"] = "https://www.atlassian.com/software/stash/downloads/binary/atlassian-bitbucket-"
        data["extention"] = "-x64.bin"
        data["service"] = "bitbucket"
        data["ip"] = "10.8.22.206"

    elif atlassian_product == "Confluence":
        data["prod_hostname"] = "Confluence"
        data["test_hostname"] = "ConfluenceTest"
        data["url"] = "https://www.atlassian.com/software/confluence/downloads/binary/atlassian-confluence-"
        data["extention"] = "-x64.bin"
        data["service"] = "confluence"
        data["ip"] = "10.8.16.249"

    else:
        print (atlassian_product + " is invalid, please enter either Jira, Confluence, Bamboo, or Bitbucket")
    
    return data

def runSaltStateSuccess(tgt, state, error_message, client):
    '''
    Will run a state and return whether it was good or not
    '''
    stateToRun = client.cmd(tgt, 'state.apply', [state])
    if not isStateSuccess(stateToRun):
        print error_message
        return False
    return True

def versiontuple(v):
    return tuple(map(int, (v.split("."))))

def isStateSuccess(minions):
    '''
    Checks if the state succeeds
    '''
    for minion in minions:
        for state in minions[minion]:
            if minions[minion][state]['result'] != True:
                print minions[minion][state]
                return False
    return True

def _pretty_list(myList):
    '''
    Takes a list of strings and returns a single string in list format.
    '''
    list_string = ""
    if len(myList) > 0:
        for i in range(len(myList)):
            list_string += myList[i]
            if i != len(myList) - 1:
                list_string += ", "
    return list_string + "\n"