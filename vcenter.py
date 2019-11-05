# -*- coding: utf-8 -*-

import subprocess
import datetime
import sys
import re
import netifaces as ni # sudo pip install netifaces
import socket
import time
import threading
import csv

# Import salt modules
import salt.client
import salt.runner

log_file_location = "/srv/logs/"
localMinion = socket.gethostname().split('.')[0]
listOfProductionMachines = ['tom-api', 'tom-apps', 'tom-cwt', 'tom-tools', 'tom-volunteer', 'tom-auth', 'tom-langprod',
                                'ngx-prod', 'ngx-tools', 'ngx-mtools', 'ngx-volunteer', 'ngx-intra']

def create_snapshots(target, snapshot_name='You_did_a_no_no'):
    '''
    Uses salt-cloud to take a snapshot of all targeted minions.
    First argument is the target minions (Uses compound targeting).
    Second argument is the name of the snapshots
    '''

    # Create Output Log File
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "create_snapshots_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: '" + target + "'"

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')

    print "Creating snapshots titled '" + snapshot_name +"' using salt-cloud"

    failures = []
    num_snapshots = 0
    num_errors = 0
    for minionID in minions:
        sys.stdout.write(minionID)
        sys.stdout.flush()
        result = subprocess.Popen(
            ["salt-cloud", "-y", "-a", "create_snapshot", minionID, "snapshot_name=" + snapshot_name, "memdump=False"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)

        if 'Snapshot created successfully' in stdout:
            print "...Success!"
            num_snapshots += 1
        else:
            output.write("\nError creating snapshot of " + minionID + "\n\n")
            print "...ERROR: PROBLEM CREATING SNAPSHOT. SEE '" + output_filename + "' FOR MORE INFORMATION"
            num_errors += 1
            failures.append(minionID)
   

    localMinion = socket.gethostname().split('.')[0]
    return_message = "Successfully created " + str(num_snapshots) + " snapshot(s) on " + localMinion + ' titled "' + snapshot_name + '"'
    if num_errors > 0:
        return_message = (return_message + "\n" + "WARNING: " + str(num_errors)
            + " snapshot(s) were unable to be created on the following VMs:\n")
        output.write('Here is the list of failures:\n')
        for fail in failures:
            output.write(fail + '\n')
            return_message += fail + '\n'

    output.close()
    
    client.cmd(localMinion, 'slack.call_hook', [return_message, 'salt'])
    return return_message


def create_snapshots_list(target):
    '''
    Uses salt-cloud to make a list of all machines that would be snapshotted using the
    given target on the create_snapshots runner.
    First argument is the target minions (Uses compound targeting).
    '''
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "create_snapshots_list_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: " + target

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')

    for minionID in minions:
        print(minionID)
    output.close()
    return None

def create_snapshot_report(target):
    '''
    Uses salt-cloud
    '''
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "create_snapshots_report_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: " + target
    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')
    minionList = list(minions.keys())
    minionList.sort()

    output.write("Pinged minions: " + str(minionList))

    cloud_client = salt.cloud.CloudClient(__opts__['conf_file'])
    result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
    snapshots = result['my-vmware-config']['vmware']
    output.write("List of all snapshots: " + str(snapshots))
    with open('/home/DevOps/snapshot_report.csv', 'wb') as csvfile:
        wrt = csv.writer(csvfile)
        headers = ["VM Name:", "Snapshot Name:", "Description:", "Snaptshot Size:", "Date Created:", "Days Old:"]
        wrt.writerow(headers)
        print "Retrieving Details on the minions..."
        minion_details = cloud_client.action(fun='show_instance', names=minionList)
        for minion in minionList:
            if minion in snapshots:
                
                minion_files = minion_details['my-vmware-config']['vmware'][minion]['files']
                snapshot_sizes = []
                for vmFile in minion_files:
                    if minion_files[vmFile]['type'] == 'diskExtent':
                        if "flat" not in minion_files[vmFile]['name'] or str(minion) + ".vmdk":
                            size_in_kb = float(minion_files[vmFile]['size'])
                            size_in_gb = size_in_kb / 1073741024
                            rounded_size = '%.2f'%size_in_gb + " GB"
                            snapshot_sizes.append(rounded_size)
                if len(snapshot_sizes) < 1:
                    for vmFile in minion_files:
                        if minion_files[vmFile]['type'] == 'diskDescriptor':
                            if "flat" not in minion_files[vmFile]['name'] or str(minion) + ".vmdk":
                                size_in_kb = float(minion_files[vmFile]['size'])
                                size_in_gb = size_in_kb / 1073741024
                                rounded_size = '%.2f'%size_in_gb + " GB"
                                snapshot_sizes.append(rounded_size)
                counter = 0
                
                for snapshot in snapshots[minion]:
                    snapShotName = snapshots[minion][snapshot]['name']
                    snapShotCreated = snapshots[minion][snapshot]['created']
                    snapShotCreatedDay = snapShotCreated.split()[0]
                    snapShotCreatedDaySplitted = snapShotCreatedDay.split('-')
                    snapShotCreatedDate = datetime.date(int(snapShotCreatedDaySplitted[0]), int(snapShotCreatedDaySplitted[1]), int(snapShotCreatedDaySplitted[2]))
                    currentDate = datetime.datetime.today().strftime('%Y-%m-%d')
                    currentDate = currentDate.split('-')
                    currentDate = datetime.date(int(currentDate[0]), int(currentDate[1]), int(currentDate[2]))
                    days_old = (currentDate - snapShotCreatedDate).days
                    snapShotDescription = snapshots[minion][snapshot]['description']
                    snapShotSize = snapshot_sizes[counter]
                    counter += 1
                    row = [str(minion), snapShotName, snapShotDescription, snapShotSize, snapShotCreatedDay, str(days_old)]
                    wrt.writerow(row)
    localMinion = socket.gethostname().split('.')[0]
    client.cmd(localMinion, 'state.apply', ['states.init.snapshot_report'])

    output.close()
    return True


def snapshot_by_name(snapshot_name):
    '''
    Uses salt-cloud
    '''
    target = "'*'"
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "create_snapshots_report_" + date + ".log"
    output = open(output_filename, "w+")

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')
    minionList = list(minions.keys())

    output.write("Pinged minions: " + str(minionList))

    cloud_client = salt.cloud.CloudClient(__opts__['conf_file'])
    result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
    snapshots = result['my-vmware-config']['vmware']

    output_string = "The following minions have a snapshot called " + snapshot_name + ":\n"

    
    for minion in minionList:
        if minion in snapshots:
            for snapshot in snapshots[minion]:
                if snapshots[minion][snapshot]['name'] == snapshot_name:
                    output_string += str(minion) + "\n"
    
    client.cmd(localMinion, 'slack.call_hook', [output_string, 'salt'])

    return output_string




def delete_snapshots(target, snapshot_name):
    '''
    Uses salt-cloud to delete a specific snapshot from of all targeted minions.
    First argument is the target minions (Uses compound targeting).
    Second argument is the name of the snapshot to delete
    '''
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "delete_snapshots_" + date + ".log"
    output = open(output_filename, "w+")

    snapshotsNotFound = []
    snapshotsNotDeleted = []
    snapshotsDeleted = []
    localMinion = socket.gethostname().split('.')[0]

    print "Fetching minions matching compound target: '" + target + "'"

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')
    minionList = list(minions.keys())

    print "Fetching list of all vCenter snapshots"

    cloud_client = salt.cloud.CloudClient(__opts__['conf_file'])
    result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
    snapshots = result['my-vmware-config']['vmware']

    print "Checking for existence of snapshots on minions"

    minionsWithSnapshot = []
    for minion in minionList:
        if minion in snapshots:
            found = False
            for snapshot in snapshots[minion]:
                if snapshots[minion][snapshot]['name'] == snapshot_name:
                    minionsWithSnapshot.append(minion)
                    found = True
                    break
            if not found:
                snapshotsNotFound.append(minion)
        else:   
            snapshotsNotFound.append(minion)

    if len(minionsWithSnapshot) > 0:
        print "Deleting snapshots titled '" + snapshot_name + "' using salt-cloud"

        args = {'snapshot_name': snapshot_name}
        # creates list of threads
        threads = []
        events = []
        
        try:
            for machine in minionsWithSnapshot:
                event = threading.Event()
                events.append(event)
                thread = threading.Thread(target=delete_snapshot, args=[machine, args, event])
                while threading.active_count() > 10:
                    time.sleep(5)
                thread.start()
                threads.append(thread)
            
            # stops further execution of script until all threads are completed. 
            for thread in threads:
                thread.join(30)
        
        except KeyboardInterrupt:
            print "Ctrl+C pressed..."
            for event in events:
                event.set()
            sys.exit(1)

        result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
        snapshots = result['my-vmware-config']['vmware']
        
        for machine in snapshots:
            for snapshot in snapshots[machine]:
                if snapshots[machine][snapshot]['name'] == snapshot_name:
                    snapshotsNotDeleted.append(machine)

        for machine in minionsWithSnapshot:
            if machine not in snapshotsNotDeleted:
                snapshotsDeleted.append(machine)

    
    if len(snapshotsNotFound) > 0:
        print "Snapshots titled " + snapshot_name + " were not found on the following minions:"
        output.write("Snapshots titled " + snapshot_name + " were not found on the following minions:\n")
        for minion in snapshotsNotFound:
            print minion
            output.write(minion + "\n")

    if len(snapshotsNotDeleted) > 0:
        print "Snapshots titled " + snapshot_name + " were unable to be deleted on the following minions:"
        output.write("Snapshots titled " + snapshot_name + " were unable to be deleted on the following minions:\n")
        for minion in snapshotsNotDeleted:
            print minion + ": " + str(result['my-vmware-config']['vmware'][minion])
            output.write(minion + ": " + str(result['my-vmware-config']['vmware'][minion]) + "\n")

    if len(snapshotsDeleted) > 0:
        print "Snapshots titled " + snapshot_name + " were deleted on the following minions:"
        output.write("Snapshots titled " + snapshot_name + " were deleted on the following minions:\n")
        for minion in snapshotsDeleted:
            print minion
            output.write(minion + "\n")

    

    output_string = ("Successfully deleted " + str(len(snapshotsDeleted)) + " snapshots, snapshots were not found on "
        + str(len(snapshotsNotFound)) + " machines, and snapshot deletion failed on " + str(len(snapshotsNotDeleted)) + " machines.")
    if snapshotsNotDeleted > 0:
        print "Those machines are: \n"
        for minion in snapshotsNotDeleted:
            output_string += minion + "\t\n"
        
        output_string += "Running Runner again to delete snapshots that failed to delete"
        output.write(output_string)
        output.close()
        
        return delete_snapshots(target, snapshot_name)
    else:
        client.cmd(localMinion, 'slack.call_hook', [output_string, 'salt'])
        output.close()
        return True


def delete_snapshots_by_name(snapshot_name):

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "delete_snapshots_by_name_" + date + ".log"
    output = open(output_filename, "w+")

    snapshotsNotDeleted = []
    snapshotsDeleted = []
    localMinion = socket.gethostname().split('.')[0]

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(localMinion, 'test.ping', tgt_type='compound')
    minionList = list(minions.keys())
    
    print "Fetching list of all vCenter snapshots"
    
    
    output.write("Collecting Snapshots")
    cloud_client = salt.cloud.CloudClient(__opts__['conf_file'])
    result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
    snapshots = result['my-vmware-config']['vmware']
    output.write("Snapshots: " + str(snapshots))
    print "Checking for existence of snapshot titled " + snapshot_name

    machinesWithSnapshot = []
    for machine in snapshots:
        for snapshot in snapshots[machine]:
            if snapshots[machine][snapshot]['name'] == snapshot_name:
                machinesWithSnapshot.append(machine)
                print machine + " has snapshot titled " + snapshot_name
    
    if len(machinesWithSnapshot) > 0:
        print "Deleting snapshots titled '" + snapshot_name + "' using salt-cloud"

        args = {'snapshot_name': snapshot_name}
        # creates list of threads
        threads = []
        events = []
        try:
            for machine in machinesWithSnapshot:
                event = threading.Event()
                events.append(event)
                thread = threading.Thread(target=delete_snapshot, args=[machine, args, event])
                thread.daemon = True
                while threading.active_count() > 10:
                    time.sleep(5)
                thread.start()
                threads.append(thread)
            
            # stops further execution of script until all threads are completed. 
            for thread in threads:
                thread.join(30) #Sets a 30 second timer to wait for a snapshot to be deleted.
                
        except KeyboardInterrupt:
            print "Ctrl+C pressed..."
            for event in events:
                event.set()
            sys.exit(1)

    result = cloud_client.action(fun='list_snapshots', provider='my-vmware-config')
    snapshots = result['my-vmware-config']['vmware']

    for machine in snapshots:
        for snapshot in snapshots[machine]:
            if snapshots[machine][snapshot]['name'] == snapshot_name:
                snapshotsNotDeleted.append(machine)

    for machine in machinesWithSnapshot:
        if machine not in snapshotsNotDeleted:
            snapshotsDeleted.append(machine)
    
    if len(snapshotsDeleted) > 0:
        print "Snapshots titled " + snapshot_name + " were deleted on the following minions:"
        output.write("Snapshots titled " + snapshot_name + " were deleted on the following minions:\n")
        for minion in snapshotsDeleted:
            print minion
            output.write(str(minion) + "\n")

    if len(snapshotsNotDeleted) > 0:
        print "Snapshots titled " + snapshot_name + " were unable to be deleted on the following minions:"
        output.write("Snapshots titled " + snapshot_name + " were unable to be deleted on the following minions:\n")
        for minion in snapshotsNotDeleted:
            fail_message = result['my-vmware-config']['vmware'][minion]
            print str(minion)
            output.write(str(minion) + ": " + str(fail_message) + "\n")

    

    output_string = ("Successfully deleted " + str(len(snapshotsDeleted)) + " snapshots, and snapshot deletion failed on " + str(len(snapshotsNotDeleted)) + " machines.")
    if len(snapshotsNotDeleted) > 0:
        print "Those machines are: \n"
        for minion in snapshotsNotDeleted:
            output_string += str(minion) + "\t\n"
        
        output_string += "Running Runner again to delete snapshots that failed to delete"
        output.write(output_string)
        output.close()
        
        return delete_snapshots_by_name(snapshot_name)
    else:
        client.cmd(localMinion, 'slack.call_hook', [output_string, 'salt'])
        output.close()
        return True

def delete_snapshot(machine, args, event):
    while not event.is_set():
        cloud_client = salt.cloud.CloudClient(__opts__['conf_file'])
        machine_list = []
        machine_list.append(machine)
        result = cloud_client.action(fun='remove_snapshot', names=machine_list, kwargs=args)
        print "Removed snapshot on " + machine
        return result

def delete_all_snapshots(target):
    '''
    Uses salt-cloud to delete all snapshots from of all targeted minions.
    First argument is the target minions (Uses compound targeting).
    '''
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "delete_all_snapshots_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: '" + target + "'"

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')

    print "Deleting all snapshots from minions matching target using salt-cloud"

    num_success = 0
    num_errors = 0
    for minionID in minions:
        sys.stdout.write(minionID)
        sys.stdout.flush()
        result = subprocess.Popen(
            ["salt-cloud", "-y", "-a", "remove_all_snapshots", minionID, "merge_snapshots=False"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)
        
        if 'removed all snapshots' in stdout:
            print "...Success!"
            num_success += 1
        else:
            output.write("\nError deleting snapshots from " + minionID + "\n\n")
            print "...ERROR: PROBLEM DELETING SNAPSHOTS. SEE '" + output_filename + "' FOR MORE INFORMATION"
            num_errors += 1
    

    return_message = "Successfully deleted all snapshots from " + str(num_success) + " machine(s)."
    if num_errors > 0:
        return_message = (return_message + "\n" + "WARNING: " + str(num_errors)
            + " machines threw errors while deleting all snapshots!")
    output.close()
    return return_message


def revert_to_snapshot(target, snapshot_name, power_on=True):
    '''
    Ultilizes salt-cloud to revert targeted minions to desired snapshot.
    If power_on is set to true, the minion will be powered on after being reverted to the snapshot
    '''
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "revert_to_snapshot_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: '" + target + "'"

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')

    print "Reverting minions to snapshot titled '" + snapshot_name + "' using salt-cloud"

    num_snapshots = 0
    num_snapshot_errors = 0
    num_power_ons = 0
    num_poweron_errors = 0
    
    for minionID in minions:
        sys.stdout.write(minionID)
        sys.stdout.flush()
        result = subprocess.Popen(["salt-cloud", "-y", "-a", "revert_to_snapshot",
                                        minionID, "snapshot_name=" + snapshot_name,
                                        "power_off=True"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)

        if 'reverted to snapshot' in stdout:
            print "...Success!"
            num_snapshots += 1
        else:
            output.write("\nError reverting to snapshot on " + minionID + "\n\n")
            print "...ERROR: PROBLEM REVERTING TO SNAPSHOT. SEE '" + output_filename + "' FOR MORE INFORMATION"
            num_snapshot_errors += 1
    

    return_message = "Successfully reverted " + str(num_snapshots) + " minion(s) to snapshot " + snapshot_name
    if num_snapshot_errors > 0:
        return_message = (return_message + "\n" + "WARNING: " + str(num_snapshot_errors)
            + " minion(s) were unable to be reverted to snapshot!")


    if power_on:
        print "Powering on minions using salt-cloud"
        for minionID in minions:
            sys.stdout.write(minionID)
            sys.stdout.flush()
            result = subprocess.Popen(["salt-cloud", "-y", "-a", "start", minionID],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stdout = result.stdout.read()
            stderr = result.stderr.read()

            output.write(stdout)
            output.write(stderr)

            if 'powered on' in stdout:
                print "...Success!"
                num_power_ons += 1
            else:
                print "...ERROR: PROBLEM POWERING ON MINION. SEE '" + output_filename + "' FOR MORE INFORMATION"
                num_poweron_errors += 1

        return_message = return_message + "\nSuccessfully powered on " + str(num_power_ons) + "minions."
        if num_poweron_errors > 0:
            return_message = (return_message + "\n" + "WARNING: " + str(num_snapshot_errors)
                + " minion(s) were unable to be powered on!")


    output.close()

    
    return return_message


def upgrade_vmware_tools(target='G@os:Windows and not G@digi:digi'):
    '''
    By default, this function will upgrade VMWare Tools on all windows VMs and WILL NOT automatically reboot.
    The target argument can be specified to target different minions. 
    '''

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "upgrade_windows_vmware_tools_" + date + ".log"
    output = open(output_filename, "w+")

    print "Fetching minions matching compound target: '" + target + "'"

    client = salt.client.LocalClient(__opts__['conf_file'])
    minions = client.cmd(target, 'test.ping', tgt_type='compound')

    print "Upgrading VMWare Tools on minions using salt-cloud"

    num_success = 0
    num_errors = 0
    failures = []

    for minionID in minions:
        sys.stdout.write(minionID)
        sys.stdout.flush()
        result = subprocess.Popen(
            ["salt-cloud", "-y", "-a", "upgrade_tools", minionID, "reboot=False"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)

        if ('VMware tools upgrade succeeded' in stdout
             or 'VMware tools is already up to date' in stdout):
            print "...Success!"
            num_success += 1
        else:
            output.write("\nError upgrading VMWare tools on " + minionID + "\n\n")
            print "...ERROR: PROBLEM UPGRADING VMWARE TOOLS. SEE '" + output_filename + "' FOR MORE INFORMATION"
            num_errors += 1
            failures.append(minionID)
   

    localMinion = socket.gethostname().split('.')[0]
    return_message = localMinion + ": Successfully upgraded VMWare Tools on " + str(num_success) + " VMs."
    if num_errors > 0:
        return_message = (return_message + "\n" + "WARNING: " + str(num_errors)
            + " VMs were unable to be upgraded to the latest version of VMWare Tools:\n")
        output.write('Here is the list of failures:\n')
        for fail in failures:
            output.write(fail + '\n')
            return_message += fail + '\n'

    output.close()
    
    client.cmd(localMinion, 'slack.call_hook', [return_message])
    return return_message




def createVM(hostname='', ip='', os='', service='', hardDisks=None, cpus=0, coresPerSocket=0, RAM=0, folder='', cluster=''):
    '''
    This function creates a VM from an exisiting template with salt installed on the template. 
    '''

    # 1. Prompt user for VM specs
    print "WARNING: All entries are case-sensitive!"
    while hostname == '':
        hostname = raw_input("Please enter the hostname of the new VM: ")

    while True:
        while ip == '':
            ip = raw_input("Please enter the IP address of the new VM (or dhcp for dynamic ip assignment): ")
        if ip == 'dhcp':
            break
        try:
            firstNumber = re.search('(\A\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip).group(1)
            secondNumber = re.search('(\A\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip).group(2)
            thirdNumber = re.search('(\A\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip).group(3)
            fourthNumber = re.search('(\A\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})', ip).group(4)
            if int(firstNumber) <= 255 and int(secondNumber) <= 255 and int(thirdNumber) <= 255 and int(fourthNumber) <= 255:
                break
        except:
            print ip + " is not a valid IP address. Please try again"
        ip = raw_input("Please enter the IP address of the new VM (or dhcp for dynamic ip assignment): ")
        
    if os == '':
        while True:
            os = raw_input("Please enter the OS of the new VM (RedHat7, RedHat8, Windows10, Windows2016, or Windows2019): ")
            if os not in ['RedHat7', 'RedHat8', 'Windows2016', 'Windows2019', 'Windows10']:
                print "Invalid OS. Please try again"
            else:
                break

    if service == '' and (os == 'RedHat7' or os == 'RedHat8') :
        while True:
            temp = raw_input("Would you like a service (tomcat, nginx, cypress, bambooagent, or sp) installed on the machine? (y/n): ")
            if temp == 'n':
                service = 'none'
                break
            elif temp == 'y':
                service = raw_input("Enter the name of the service (tomcat, nginx, cypress, bambooagent, or sp): ")
                if service not in ['tomcat', 'nginx', 'cypress', 'bambooagent', 'sp']:
                    print "That is not a valid service. Please try again."
                else:
                    break
    if os == 'RedHat7' or os == 'RedHat8':
        print "Default Hardware:\n\tHard Disks:\n\t\tHD1 - 500GB\n\tCPUs: 2\n\tCores Per Socket: 1\n\tRAM: 2GB"
    elif os == 'Windows10':
        print "Default Hardware:\n\tHard Disks:\n\t\tHD1 - 500GB\n\tCPUs: 2\n\tCores Per Socket: 1\n\tRAM: 8GB"
    else:
        print "Default Hardware:\n\tHard Disks:\n\t\tHD1 - 500GB\n\t\tHD2 - 500GB\n\tCPUs: 2\n\tCores Per Socket: 1\n\tRAM: 8GB"
    while True:
        customizeHardware = raw_input("Would you like to customize this hardware? (y/n): ")
        if customizeHardware == 'n':
            customize = False
            break
        elif customizeHardware == 'y':
            customize = True
            break
        else:
            print "I'm sorry, that is an invalid answer. Please try again."
        
    if customize:
        if not hardDisks:
            temp = raw_input("Would you like to customize the hard drives on the machine? The default is one Hard Disk with 500GBs. (y/n): ")
            if temp == 'y':
                hardDisks = []
                hardDiskNumber = 1
                while True:
                    temp = raw_input("Enter capacity for hard drive number " + str(hardDiskNumber) + "(in GB): ")
                    hardDisks.append((temp, hardDiskNumber))
                    temp = raw_input("Would you like any more additional hard drives on the machine? (y/n): ")
                    if temp == 'n':
                        break
                    else:
                        hardDiskNumber += 1
        
        if cpus == 0:
            cpus = checkValueIsNumGreaterOrEqualToZero("Enter the number of CPUs for the new VM (0 for a default of 2): ")
           
        if coresPerSocket == 0:
            coresPerSocket = checkValueIsNumGreaterOrEqualToZero("Enter the number of Cores per Socket for the new VM (0 for a default of 1): ")

        if RAM == 0:
            RAM = checkValueIsNumGreaterOrEqualToZero("Enter the number of GB of RAM for the new VM (0 for a default of 2): ")

    if folder == '':
        folder = raw_input("Enter the name of the vCenter folder to put the machine in. No path traversal necessary, only the folder name is needed. (none for default DevOps_Area51 folder): ")

    # if cluster == '':
    #     while True:
    #         cluster = raw_input("Enter the name of the cluster to put the new machine on (compellent cluster, vsan1, or vsan2). No default option. If unsure, work with supervisor: ")
    #         if cluster not in ['compellent cluster', 'vsan1', 'vsan2']:
    #             print "Invalid cluster. Please try again."
    #         else:
    #             break
    cluster = 'compellent cluster'
    datastore = 'C7020Cluster'
    
    confirmation_string = "Please confirm you want a VM created with the following options:\nHostname: " + hostname + "\nIP: " + ip + "\nOS: " + os
    if os == 'RedHat7' or os == 'RedHat8':
        if service != '':
            confirmation_string += "\nService: " + service
        else:
            confirmation_string += "\nService: NONE" 
    confirmation_string += "\nHard Disks:"
    if not not hardDisks:
        for hardDisk in hardDisks:
            confirmation_string += "\t\nHD" + hardDisk[0] + ": " + hardDisk[1] + "GBs"
    else:
        confirmation_string += "\n\t\tHD1 - 500GBs"

    
    if cpus != 0:
        confirmation_string += "\nCPUs: " + cpus
    else:
        confirmation_string += "\nCPUs: 2"

    if coresPerSocket != 0:
        confirmation_string += "\nCores Per Socket: " + coresPerSocket
    else:
        confirmation_string += "\nCores Per Socket: 1"

    if folder == '':
        confirmation_string += "\nFolder: DevOps_Area51"
    else:
        confirmation_string += "\nFolder: " + folder
    
    confirmation_string += "\nCluster: " + cluster + "\nDatastore: " + datastore + " (y/n): "

    while True:
        confirmation = raw_input(confirmation_string)
        if confirmation == 'y':
            print "Procceding..."
            break
        elif confirmation == 'n':
            print "Aborting VM Creation..."
            return False   
        else:
            print "Invalid answer. Please try again."
            continue

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "create_VM_" + date + ".log"
    output = open(output_filename, "w+")

    # 2. Use salt-cloud to create new VM

    # Update the salt bootstrap
    subprocess.call(["salt-cloud", "-u"], stdout=output, stderr=output)

    # Clone from specified machine and install salt
    print "Beginning cloning process."
    if 'Windows' in os:
        createCloudProfileWindows(hostname, ip, cluster, datastore, os + "-Vanilla", cpus, coresPerSocket, RAM, folder, hardDisks)
        result = subprocess.Popen(
            ["salt-cloud", "-p", hostname, hostname],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)

        if hostname + ' already exists' in stdout:
            print ("A VM in vCenter already exists with the name " + hostname
                + ". Please choose a different name and try again.")
            return False
        elif hostname + ":" in stdout:
            print "Machine successfully created.\n"
        else:
            print "An ERROR occurred. See " + output_filename + " for more information."
            return False

        # Close off port 445 now that salt is installed
        time.sleep(20)
        print "Securing port 445 on new minion"
        client = salt.client.LocalClient(__opts__['conf_file'])
        result1 = client.cmd(hostname, 'firewall.delete_rule', ['Salt Bootstrap Inbound'])
        result2 = client.cmd(hostname, 'firewall.delete_rule', ['Salt Bootstrap Outbound'])
        if not result1[hostname] or not result2[hostname]:
            print "An error occurred while securing the port!"
            return False

        print "Changing hostname"
        result = client.cmd(hostname, 'system.set_computer_name', [hostname])

        print "Joining new VM to ad.mtc.byu.edu domain"
        result = client.cmd(hostname, 'state.apply', ['states.init.join_domain'])
        if not isStateSuccess(result):
            print "An error occured while joining the domain"
            return False

        print "Rebooting VM"
        result = client.cmd(hostname, 'system.reboot')
        if not result[hostname]:
            print "An error occured while rebooting the VM"
            return False

        print "Machine created successfully"
        return True


    elif os == 'RedHat7' or os == 'RedHat8':
        if os == 'RedHat7':
            template = 'redhattemplate7'
        else:
            template = 'redhattemplate8'
        gateway = createCloudProfileRedHat(hostname, ip, cluster, datastore, template, cpus, coresPerSocket, RAM, folder, hardDisks)
        result = subprocess.Popen(
            ["salt-cloud", "-p", hostname, hostname],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout = result.stdout.read()
        stderr = result.stderr.read()

        output.write(stdout)
        output.write(stderr)

        if 'ERROR: Failed to run install_red_hat_enterprise_linux_stable_deps()!!!' in stdout:
            print "Template is not subscribed to RedHat servers. Resubscribe the template and try again."
            return False
        elif hostname + ' already exists' in stdout:
            print ("A VM in vCenter already exists with the name " + hostname
                + ". Please choose a different name and try again.")
            return False
        elif hostname + ":" in stdout:
            print "Machine successfully created.\n"
        else:
            print "An ERROR occurred. See " + output_filename + " for more information."
            return False

        # 4. Sync new pillars, update hostname and IP, and reboot machine
        client = salt.client.LocalClient(__opts__['conf_file'])

        if ip == 'dhcp':
            print "Updating hostname and network config of " + hostname
            # Set needed grains
            client.cmd(hostname, 'test.ping', tgt_type='compound')
            client.cmd(hostname, 'grains.setval', ['new_hostname', hostname])
            # Update hostname and network config
            minions = client.cmd(hostname, 'state.apply', ['states.init.hostDHCP'])
            if not isStateSuccess(minions):
                print "Error updating Hostname and network config of " + hostname

        else:
            print "Updating Hostname and IP Address of " + hostname
            # Set needed grains
            client.cmd(hostname, 'grains.setval', ['new_hostname', hostname])
            client.cmd(hostname, 'grains.setval', ['new_ip', ip])
            client.cmd(hostname, 'grains.setval', ['new_gateway', gateway])

            # Update host and IP.
            minions = client.cmd(hostname, 'state.apply', ['states.init.hostIP'])
            if not isStateSuccess(minions):
                print "Error updating Hostname and IP Address of " + hostname

        # 5. Wait for machine to reboot and reconnect to master
        print "Waiting for " + hostname + " to reboot and reconnect to salt-master.\n"
        runnerClient = salt.runner.RunnerClient(__opts__)
        runnerClient.cmd('state.event', ['salt/minion/' + hostname + '/start', 1, False], print_event=False)

        # 6. Change passwords, update repos, run updates, and install services
        print "Updating Repos.\n"
        minions = client.cmd(hostname, 'state.apply', ['states.init.update_repos'])
        if not isStateSuccess(minions):
            print "Error Updating Repos.\n"
            #return False

        print "Updating users and passwords."
        minions = client.cmd(hostname, 'state.apply', ['states.init.users'])
        if not isStateSuccess(minions):
            print "Error Updating passwords."
            #return False

        print "Running Updates.\n"
        minions = client.cmd(hostname, 'state.apply', ['states.init.uptodate'])
        if not isStateSuccess(minions):
            print "Error Running Updates.\n"
            #return False

        print "Syncing salt custom modules"
        minions = client.cmd(hostname, 'saltutil.sync_all')

        if service in ['tomcat', 'cypress', 'sp']:
            print "Installing Java.\n"
            minions = client.cmd(
                hostname,
                'cmd.run',
                ['yum install -y java-1.8.0-openjdk java-1.8.0-openjdk-headless']
            )
            # if not isStateSuccess(minions):
            #     print "Error Installing Java.\n"
            #     return False
    
        if service == 'cypress':
            print "Installing tomcat."
            minions = client.cmd(hostname, 'state.apply', ['states.tomcat.install'])
            if not isStateSuccess(minions):
                print "Error Installing tomcat.\n"

            print "Deploying tomcat property files"
            runnerClient.cmd('bamboo.deploy', [hostname, 'Tomcat Properties DevProd'])

            print "Installing nginx."
            minions = client.cmd(hostname, 'state.apply', ['states.nginx.install'])
            if not isStateSuccess(minions):
                print "Error Installing nginx.\n"

            print "Installing cypress docker image and cypress beacon."
            minions = client.cmd(hostname, 'state.apply', ['states.cypress.install'])
            if not isStateSuccess(minions):
                print "Error Installing cypress.\n"
            minions = client.cmd(hostname, 'state.apply', ['states.cypress.beacons.new-build'])
            if not isStateSuccess(minions):
                print "Error Installing cypress beacon.\n"
            

        elif service == 'bambooagent':
            print "Installing bamboo agent service"
            minions = client.cmd(hostname, 'state.apply', ['states.bamboo.agent'])
            if not isStateSuccess(minions):
                print "Error Installing bamboo agent service.\n"

        elif service != 'none':
            print "Installing " + service + ".\n"
            minions = client.cmd(hostname, 'state.apply', ['states.' + service + '.install'])
            if not isStateSuccess(minions):
                print "Error Installing " + service + ".\n"
                #return False

        if service == 'sp':
            print "Deploying SP Application"
            runnerClient.cmd('bamboo.deploy', [hostname, 'SP'])


        # 8. Configure F5

        print "Success!!\n"
        print hostname + " is being rebooted."
        minions = client.cmd(hostname, 'state.apply', ['states.util.reboot'])
        return True
    else:
        print "Invalid OS selected"
        return False


def replaceVM(hostname, cluster='compellent cluster', ip='none'):
    '''
    Given the hostname of a tomcat or nginx server, the runner will power off
    the current server and replace it with a new VM.
    '''

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M")
    output_filename = log_file_location + "replace_VM_" + date + ".log"
    output = open(output_filename, "w+")

    if hostname[:3] == 'tom':
        service = 'tomcat'
    else:
        service = 'nginx'

    client = salt.client.LocalClient(__opts__['conf_file'])

    if ip == 'none':
        print "Acquiring IP address of " + hostname
        minions = client.cmd(hostname, 'grains.item', ['fqdn_ip4'])
        for minion in minions:
            try:
                ip = (minions[minion].get('fqdn_ip4'))[0]
            except AttributeError:
                print "Minion did not respond."
        if ip == 'none':
            ip = raw_input("Unable to obtain IP through salt query. Please Enter the IP address of "
                            + hostname + ": ")
        print "IP Address: " + ip + "\n"

    print "Decommissioning old VM - " + hostname

    # Force machine offline in F5
    # print "Forcing offline " + hostname + " in the F5"
    # minions = client.cmd(hostname, 'state.apply', ['states.f5.force_offline'])
    # if not isStateSuccess(minions):
    #     print "Unable to force offline " + hostname + ". Verify the F5 grains on this minion."

    # Power off machine with salt-cloud
    print "Shutting Down Guest OS of " + hostname
    result = subprocess.Popen(
        ["salt-cloud", "-y", "-a", "stop", hostname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout = result.stdout.read()
    stderr = result.stderr.read()
    output.write(stdout)
    output.write(stderr)

    if 'powered off' in stdout:
        print hostname + " powered-off"
    else:
        print "Unable to power-off " + hostname
        return False

    # Move and Rename machine with salt-cloud
    print "Moving " + hostname + " to DevOps_Archive"
    result = subprocess.Popen(
        ["salt-cloud", "-y", "-a", "move", hostname, "new_folder=DevOps_Archive"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout = result.stdout.read()
    stderr = result.stderr.read()
    output.write(stdout)
    output.write(stderr)

    if 'move successful' in stdout:
        print hostname + " moved to DevOps_Archive"
    else:
        print "Unable to move " + hostname
        return False

    print "Renaming " + hostname + " to " + hostname + "-old"
    result = subprocess.Popen(
        ["salt-cloud", "-y", "-a", "rename", hostname, "new_name=" + hostname + "-old"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout = result.stdout.read()
    stderr = result.stderr.read()
    output.write(stdout)
    output.write(stderr)

    if 'rename successful' in stdout:
        print hostname + " renamed"
    else:
        print "Unable to rename " + hostname
        return False

    # Step 2: Create new machine
    # Create the Salt-Cloud profile
    folder = 'Dev'
    for machine in listOfProductionMachines:
        if machine in hostname:
            folder = 'Prod'

    if service == 'tomcat':
        RAM = 4
        folder = folder + 'Tomcat'
        repo_path = '/var/lib/tomcat'
        repo_folder = 'webapps'
    else:
        RAM = 2
        folder = folder + 'Nginx'
        repo_path = '/'
        repo_folder = 'cdn'

    # Update the salt bootstrap
    subprocess.call(["salt-cloud", "-u"], stdout=output, stderr=output)

    # Clone from specified machine and install salt
    print "\nCreating VM with Salt-Cloud"
    gateway = createCloudProfileRedHat(hostname, ip, cluster, 'C7020Cluster', 'redhattemplate7', 0, 0, RAM, folder)
    result = subprocess.Popen(
        ["salt-cloud", "-p", hostname, hostname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout = result.stdout.read()
    stderr = result.stderr.read()

    output.write(stdout)
    output.write(stderr)

    if 'ERROR: Failed to run install_red_hat_enterprise_linux_stable_deps()!!!' in stdout:
        print "Template is not subscribed to RedHat servers. Resubscribe the template and try again."
        return False
    elif hostname + ' already exists' in stdout:
        print ("A VM in vCenter already exists with the name " + hostname
            + ". Please choose a different name and try again.")
        return False
    elif hostname + ":" in stdout:
        print "Machine successfully created.\n"
    else:
        print "An ERROR occurred. See " + output_filename + " for more information."
        return False

    # 4. Sync new pillars, update hostname and IP, and reboot machine
    print "Updating Hostname and IP Address of " + hostname
    client = salt.client.LocalClient(__opts__['conf_file'])
    # Set needed grains
    client.cmd(hostname, 'grains.setval', ['new_hostname', hostname])
    client.cmd(hostname, 'grains.setval', ['new_ip', ip])
    client.cmd(hostname, 'grains.setval', ['new_gateway', gateway])

    # Update host and IP.
    minions = client.cmd(hostname, 'state.apply', ['states.init.hostIP'])
    if not isStateSuccess(minions):
        print "Error updating Hostname and IP Address of " + hostname

    # 5. Wait for machine to reboot and reconnect to master
    print "Waiting for " + hostname + " to reboot and reconnect to salt-master."
    runnerClient = salt.runner.RunnerClient(__opts__)
    runnerClient.cmd('state.event', ['salt/minion/' + hostname + '/start', 1, False], print_event=False)

    # 6. Change passwords, update repos, run updates, and install services
    print "Updating Repos."
    minions = client.cmd(hostname, 'state.apply', ['states.init.update_repos'])
    if not isStateSuccess(minions):
        print "Error Updating Repos."
        #return False

    print "Updating users and passwords."
    minions = client.cmd(hostname, 'state.apply', ['states.init.users'])
    if not isStateSuccess(minions):
        print "Error Updating passwords."
        #return False

    print "Running Updates."
    minions = client.cmd(hostname, 'state.apply', ['states.init.uptodate'])
    if not isStateSuccess(minions):
        print "Error Running Updates."
        #return False

    print "Syncing salt custom modules"
    minions = client.cmd(hostname, 'saltutil.sync_all')


    # Add Dynatrace installation to production machines
    if hostname[:-1] in listOfProductionMachines or 'support' in hostname:
        print "Installing Dynatrace"
        minions = client.cmd(hostname, 'state.apply', ['states.dynatrace.install'])


    if service == 'tomcat':
        print "Installing Java."
        minions = client.cmd(
            hostname,
            'cmd.run',
            ['yum install -y java-1.8.0-openjdk java-1.8.0-openjdk-headless']
        )


    print "Installing " + service
    minions = client.cmd(hostname, 'state.apply', ['states.' + service + '.install'])
    if not isStateSuccess(minions):
        print "Error Installing " + service + ".\n"
        #return False 

    # Deploy beacons to tomcat machines
    if service == 'tomcat':
        print "Deploying tomcat beacons"
        minions1 = client.cmd(hostname, 'state.apply', ['states.tomcat.beacons.severe-errors'])
        minions2 = client.cmd(hostname, 'state.apply', ['states.tomcat.beacons.severe-errors'])
        if not isStateSuccess(minions1) or not isStateSuccess(minions2):
            print "WARNING: Error deploying tomcat beacons"

    # If this is a tomcat api machine then configure isilon mount
    if hostname[:7] == 'tom-api':
        print "Applying special configs for tom-api machines."
        minions = client.cmd(hostname, 'state.apply', ['states.tomcat.api'])
        if not isStateSuccess(minions):
            print "Error Applying special configs for tom-api machines!!!!!!!! " + service + ".\n"

    if hostname[:8] == 'ngx-prod':
        print "Applying special configs for ngx-prod machines."
        minions = client.cmd(hostname, 'state.apply', ['states.nginx.prod'])
        if not isStateSuccess(minions):
            print "Error Installing Applying special configs for ngx-prod machines!!!!!" + service + ".\n"

    if hostname[:12] == 'tom-langprod':
        print "Applying special configs for tom-langprod machines."
        minions = client.cmd(hostname, 'state.apply', ['states.tomcat.prodlang'])
        if not isStateSuccess(minions):
            print "Error Applying special configs for tom-langprod machines!!!!" + service + ".\n"

    if hostname[:8] != 'ngx-prod':
        subprocess.call(['ssh-keygen', '-R', hostname], stdout=output, stderr=output)
        subprocess.call(['ssh-keygen', '-R', ip], stdout=output, stderr=output)
        known_hosts = open('/root/.ssh/known_hosts', 'a+')
        subprocess.call(['ssh-keyscan', '-H', hostname], stdout=known_hosts, stderr=output)
        known_hosts.close()
        result = subprocess.call(["rsync", "-av", "/repo/" + hostname + "/" + repo_folder,
                                  "BambooDeploy@" + hostname + ":" + repo_path],
                                  stdout=output, stderr=output)
        if result == 0:
            if service == 'tomcat':
                print "Changing owner of webapps"
                client.cmd(hostname, 'cmd.run', ['chown -R tomcat:tomcat /var/lib/tomcat/webapps'])
            print "Successfully deployed web applications to " + hostname
        else:
            return "rsync of webapps failed to " + hostname + "!!!" 

    # Run Bamboo Deployments FIXME: add error checking
    print "Running Bamboo Configuration Deployment"
    if service == 'tomcat' and 'lang' not in hostname and hostname[:8] != 'tom-auth':
        if hostname[:-1] in listOfProductionMachines:
            runnerClient.cmd('bamboo.deploy', [hostname, 'Tomcat Properties Files --PROD--'])
        else:
            runnerClient.cmd('bamboo.deploy', [hostname, 'Tomcat Properties DevProd'])
    elif service == 'nginx':
        runnerClient.cmd('bamboo.deploy', [hostname, 'NGINX Configs'])

    # Reboot Machine and declare victory
    minions = client.cmd(hostname, 'state.apply', ['states.util.reboot'])

    return hostname + " has been successfully replaced and is being rebooted."


# Helper Functions *******************************************************************************************************
VCENTER_PROVIDER = "my-vmware-config"

clusters = {
    'compellent cluster'  : 'Production',
    'vsan1'       : 'Production-vSAN',
    'vsan2'       : 'Production-vSAN2',
    'ressurected' : 'Production-Res'
}

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

def createCloudProfileRedHat(hostname, ip, cluster, datastore, cloneFrom, cpus=0, coresPerSocket=0, RAM=0, folder='', hardDisks=None):
    # Create the Salt-Cloud profile. Returns the gateway used.

    RESOURCE_POOL = clusters[cluster]
    MASTER_IP = ni.ifaddresses('ens192')[ni.AF_INET][0]['addr'] # Grabs IP of current machine

    runnerClient = salt.runner.RunnerClient(__opts__)
    pillars = runnerClient.cmd('pillar.show_pillar', print_event=False)
    ROOT_PASSWORD = pillars['some_secret_password'] # SSH keys is another option

    gateway = None
    networkInterface = None

    if ip == 'dhcp':
        networkInterface = 'dvVLAN518 10.5.16.0 (1)'
    else:
        shorterIP = re.search('\A\d{1,3}\.\d{1,3}\.\d{1,3}', ip).group(0)
        if not shorterIP:
            print "Invalid IP Address!"
            return False

        if shorterIP == '128.187.34':  # Account for special case of the split 128.187.34
            fourthNumber = re.search('(\A\d{1,3}\.\d{1,3}\.\d{1,3})(\.\d{1,3})', ip).group(1)
            if int(fourthNumber) <= 126:
                gateway = '128.187.34.1'
                networkInterface = 'dvVLAN718 128.187.34.0 25 (1)'
            else:
                gateway = '128.187.34.129'
                networkInterface = 'dvVLAN719 128.187.34.128 25 (1)'
        else:
            gateway = (networkInterfaces[shorterIP])[0]
            networkInterface = networkInterfaces[shorterIP][1]
    
    confFile = open("/etc/salt/cloud.profiles.d/" + hostname + ".conf", "w+")
    confFile.write(hostname + ":\n")
    confFile.write("   provider: " + VCENTER_PROVIDER + "\n")
    confFile.write("   resourcepool: " + RESOURCE_POOL + "\n")
    confFile.write("   cluster: " + cluster + "\n")
    confFile.write("   datastore: " + datastore + "\n")
    confFile.write("   clonefrom: " + cloneFrom + "\n")
    confFile.write("   minion:\n")
    confFile.write("      master: " + MASTER_IP + "\n")
    confFile.write("      id: " + hostname + "\n")
    confFile.write("   password: " + ROOT_PASSWORD + "\n")

    confFile.write("   devices:\n")
    confFile.write("      network:\n")
    confFile.write("         Network adapter 1:\n")
    confFile.write("            name: " + networkInterface + "\n")
    confFile.write("            switch_type: distributed\n")
    if cloneFrom == "redhattemplate8":
        confFile.write("   script: bootstrap-salt.sh -x python3\n")
    if ip != 'dhcp':
        confFile.write("            ip: " + ip + "\n")
        confFile.write("            gateway: [" + gateway + "]\n")
        confFile.write("            subnet_mask: 255.255.255.0\n")
        confFile.write("            domain: mtc.byu.edu\n")

    if hardDisks:
        confFile.write("      disk:\n")
        for disk in hardDisks:
            confFile.write("         Hard disk " + str(disk[1]) + ":\n")
            confFile.write("            size: " + disk[0] + "\n")
            confFile.write("            thin_provision: True\n")

    confFile.write("   domain: mtc.byu.edu\n")
    confFile.write("   dns_servers:\n")
    confFile.write("      - 10.8.16.99\n")
    confFile.write("      - 10.8.16.185\n")

    if cpus != 0:
        confFile.write("   num_cpus: " + str(cpus) + "\n")

    if coresPerSocket != 0:
        confFile.write("   cores_per_socket: " + str(coresPerSocket) + "\n")

    if RAM != 0:
        confFile.write("   memory: " + str(RAM) + "GB\n")

    if folder == '':
        confFile.write("   folder: DevOps_Area51")
    else:
        confFile.write("   folder: " + folder)

    confFile.close()

    return gateway


def createCloudProfileWindows(hostname, ip, cluster, datastore, cloneFrom, cpus=0, coresPerSocket=0, RAM=0, folder='', hardDisks=None):

    RESOURCE_POOL = clusters[cluster]
    MASTER_IP = ni.ifaddresses('ens192')[ni.AF_INET][0]['addr'] # Grabs IP of current machine

    runnerClient = salt.runner.RunnerClient(__opts__)
    pillars = runnerClient.cmd('pillar.show_pillar', print_event=False)
    ROOT_PASSWORD = pillars['Somesecretpassword'] # SSH keys is another option

    gateway = None
    networkInterface = None

    if ip == 'dhcp':
        networkInterface = 'dvVLAN518 10.5.16.0 (1)'
    else:
        shorterIP = re.search('\A\d{1,3}\.\d{1,3}\.\d{1,3}', ip).group(0)
        if not shorterIP:
            print "Invalid IP Address!"
            return False

        if shorterIP == '128.187.34':  # Account for special case of the split 128.187.34
            fourthNumber = re.search('(\A\d{1,3}\.\d{1,3}\.\d{1,3})(\.\d{1,3})', ip).group(1)
            if int(fourthNumber) <= 126:
                gateway = '128.187.34.1'
                networkInterface = 'dvVLAN718 128.187.34.0 25 (1)'
            else:
                gateway = '128.187.34.129'
                networkInterface = 'dvVLAN719 128.187.34.128 25 (1)'
        else:
            gateway = (networkInterfaces[shorterIP])[0]
            networkInterface = networkInterfaces[shorterIP][1]
    
    confFile = open("/etc/salt/cloud.profiles.d/" + hostname + ".conf", "w+")
    confFile.write(hostname + ":\n")
    confFile.write("   provider: " + VCENTER_PROVIDER + "\n")
    confFile.write("   resourcepool: " + RESOURCE_POOL + "\n")
    confFile.write("   cluster: " + cluster + "\n")
    confFile.write("   datastore: " + datastore + "\n")
    confFile.write("   clonefrom: " + cloneFrom + "\n")
    confFile.write("   minion:\n")
    confFile.write("      master: " + MASTER_IP + "\n")
    confFile.write("      id: " + hostname + "\n")
    confFile.write("   win_username: User\n")
    confFile.write("   win_password: " + ROOT_PASSWORD + "\n")
    confFile.write("   win_installer: /srv/salt/minion_installer/saltwin.exe\n")
    confFile.write("   plain_text: True\n")

    confFile.write("   devices:\n")
    confFile.write("      network:\n")
    confFile.write("         Network adapter 1:\n")
    confFile.write("            name: " + networkInterface + "\n")
    confFile.write("            switch_type: distributed\n")
    if ip != 'dhcp':
        confFile.write("            ip: " + ip + "\n")
        confFile.write("            gateway: [" + gateway + "]\n")
        confFile.write("            subnet_mask: 255.255.255.0\n")
        confFile.write("            domain: ad.mtc.byu.edu\n")

    if hardDisks:
        confFile.write("      disk:\n")
        for disk in hardDisks:
            confFile.write("         Hard disk " + str(disk[1]) + ":\n")
            confFile.write("            size: " + disk[0] + "\n")
            confFile.write("            thin_provision: True\n")

    confFile.write("   domain: ad.mtc.byu.edu\n")
    confFile.write("   dns_servers:\n")
    confFile.write("      - 10.8.16.99\n")
    confFile.write("      - 10.8.16.185\n")

    if cpus != 0:
        confFile.write("   num_cpus: " + str(cpus) + "\n")

    if coresPerSocket != 0:
        confFile.write("   cores_per_socket: " + str(coresPerSocket) + "\n")

    if RAM != 0:
        confFile.write("   memory: " + str(RAM) + "GB\n")

    if folder == '':
        confFile.write("   folder: DevOps_Area51")
    else:
        confFile.write("   folder: " + folder)

    confFile.close()

def checkValueIsNumGreaterOrEqualToZero(prompt):
    while True:
        try:
            value = int(raw_input(prompt))
        except ValueError:
            print "Invalid value entered."
        else:
            if value >= 0:
                break
            else:
                print "Number must be greater than or equal to 0"
    return value

def isStateSuccess(minions):
    for minion in minions:
        for state in minions[minion]:
            if minions[minion][state]['result'] != True:
                return False
    return True