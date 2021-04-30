import BioSimSpace as BSS
from BioSimSpace import _Exceptions
import sys
import csv
print(BSS.__version__)

print ("%s %s %s" % (sys.argv[0],sys.argv[1],sys.argv[2]))

# Load equilibrated free inputs for both ligands. Complain if input not found. These systems already contain equil. waters.
print(f"Loading ligands {sys.argv[1]} and {sys.argv[2]}.")
ligs_path = "inputs/ligands/"
ligand_1 = BSS.IO.readMolecules([f"{ligs_path}{sys.argv[1]}_lig_equil_solv.rst7", f"{ligs_path}{sys.argv[1]}_lig_equil_solv.prm7"])
ligand_2 = BSS.IO.readMolecules([f"{ligs_path}{sys.argv[2]}_lig_equil_solv.rst7", f"{ligs_path}{sys.argv[2]}_lig_equil_solv.prm7"])

# Extract ligands.
ligand_1 = ligand_1.getMolecule(0)
ligand_2 = ligand_2.getMolecule(0)

# Extract ions.
ions_free += ligand_2.search("not mols with atomidx 2")

# Align ligand1 on ligand2
print("Mapping and aligning..")
print(ligand_1, ligand_2)
mapping = BSS.Align.matchAtoms(ligand_1, ligand_2, sanitize=True, complete_rings_only=True)
ligand_1_a = BSS.Align.rmsdAlign(ligand_1, ligand_2, mapping)

# Generate merged molecule.
print("Merging..")
merged_ligs = BSS.Align.merge(ligand_1_a, ligand_2, mapping)


################ now repeat above steps, but for the protein + ligand systems.
# Load equilibrated bound inputs for both ligands. Complain if input not found
print(f"Loading bound ligands {sys.argv[1]} and {sys.argv[2]}.")
ligs_path = "inputs/protein/"
system_1 = BSS.IO.readMolecules([f"{ligs_path}{sys.argv[1]}_sys_equil_solv.rst7", f"{ligs_path}{sys.argv[1]}_sys_equil_solv.prm7"])
system_2 = BSS.IO.readMolecules([f"{ligs_path}{sys.argv[2]}_sys_equil_solv.rst7", f"{ligs_path}{sys.argv[2]}_sys_equil_solv.prm7"])

# Extract ligands and protein. Do this based on nAtoms and nResidues, as sometimes
# the order of molecules is switched, so we can't use index alone.
system_ligand_1 = None
n_residues = [mol.nResidues() for mol in system_1]
n_atoms = [mol.nAtoms() for mol in system_1]
for i, (n_resi, n_at) in enumerate(zip(n_residues[:20], n_atoms[:20])):
    if n_resi == 1 and n_at > 5:
        system_ligand_1 = system_1.getMolecule(i)
    else:
        pass

# loop over molecules in system to extract the ligand and the protein. 
system_ligand_2 = None
protein = None

n_residues = [mol.nResidues() for mol in system_2]
n_atoms = [mol.nAtoms() for mol in system_2]
for i, (n_resi, n_at) in enumerate(zip(n_residues, n_atoms)):
    # grab the system's ligand and the protein. ignore the waters.
    if n_resi == 1 and n_at > 5:
        system_ligand_2 = system_2.getMolecule(i)
    elif n_resi > 1:
        protein = system_2.getMolecule(i)
    else:
        pass

# extract ions.
ions_bound = system_2.search("not mols with atomidx 2")

if system_ligand_1 and system_ligand_2 and protein:
    print("Using molecules ligand_1, ligand_2, protein:")
    print(system_ligand_1, system_ligand_2, protein)
else:
    raise _Exceptions.AlignmentError("Could not extract ligands or protein from input systems. Check that your ligands/proteins are properly prepared by BSSligprep.sh!")

# Align ligand1 on ligand2
print("Mapping..")
mapping = BSS.Align.matchAtoms(system_ligand_1, system_ligand_2, sanitize=True, complete_rings_only=True)

print("Aligning..")
system_ligand_1_a = BSS.Align.rmsdAlign(system_ligand_1, system_ligand_2, mapping)

# Generate merged molecule.
print("Merging..")
system_merged_ligs = BSS.Align.merge(system_ligand_1_a, system_ligand_2, mapping)



#### Get equilibrated waters and waterbox information for both bound and free. Get all information from lambda==1
waters_free = ligand_2.getWaterMolecules()
waterbox_free = ligand_2.getBox()

waters_bound = system_2.getWaterMolecules()
waterbox_bound = system_2.getBox()

# now make final systems with merged, the equil. protein of lambda==1 and equil. waters of lambda==1.
system_free = merged_ligs + ions_free + waters_free
system_bound = system_merged_ligs + protein + ions_bound + waters_bound

# restore box information.
system_free.setBox(waterbox_free)
system_bound.setBox(waterbox_bound)







########################### now set up the SOMD or GROMACS MD directories. 
#first, figure out which engine and what runtime the user has specified in protocol.
stream = open("protocol.dat","r")
lines = stream.readlines()

### get the requested engine.
engine_query = lines[7].rstrip().replace(" ","").split("=")[-1].upper()
if engine_query not in ["SOMD", "GROMACS"]:
    raise NameError("Input MD engine not recognised. Please use any of ['SOMD', 'GROMACS']" \
    +"on the eighth line of protocol.dat in the shape of (e.g.):\nengine = SOMD")

### get the requested runtime.
runtime_query = lines[6].rstrip().replace(" ","").split("=")[-1].split("*")[0]
try:
    runtime_query = int(runtime_query)
except ValueError:
    raise NameError("Input runtime value not supported. Please use an integer" \
    +" on the seventh line of protocol.dat in the shape of (e.g.):\nsampling = 2*ns")

# make sure user has set ns or ps.
runtime_unit_query = lines[6].rstrip().replace(" ","").split("=")[-1].split("*")[1]
if runtime_unit_query not in ["ns", "ps"]:
    raise NameError("Input runtime unit not supported. Please use 'ns' or 'ps'" \
    +" on the seventh line of protocol.dat in the shape of (e.g.):\nsampling = 2*ns")

if runtime_unit_query == "ns":
    runtime_unit = BSS.Units.Time.nanosecond
elif runtime_unit_query == "ps":
    runtime_unit = BSS.Units.Time.picosecond

### get the number of lambda windows for this pert.
num_lambda = None
with open("network.dat", "r") as lambdas_file:
    reader = csv.reader(lambdas_file, delimiter=" ")
    for row in reader:

        if (row[0] == sys.argv[1] and row[1] == sys.argv[2]) or \
        (row[1] == sys.argv[1] and row[0] == sys.argv[2]):
            num_lambda = int(row[2])
if not num_lambda:
    raise NameError(f"The perturbation {sys.argv[1]}~{sys.argv[2]} (or the reverse) was not found in network.dat.")

# define the free energy protocol with all this information. User could customise settings further here, see docs.
freenrg_protocol = BSS.Protocol.FreeEnergy(num_lam=num_lambda, runtime=runtime_query*runtime_unit)


############# Set up the directory environment.
# testing is already done by BSS.
print(f"Setting up {engine_query} directory environment in outputs/{engine_query}/{sys.argv[1]}~{sys.argv[2]}.")
# set up a SOMD bound+free folder with standard settings.
print("Bound..")
BSS.FreeEnergy.Binding(
                    system_bound, 
                    freenrg_protocol, 
                    engine=f"{engine_query}",
                    work_dir=f"outputs/{engine_query}/{sys.argv[1]}~{sys.argv[2]}"
)

# set up a SOMD free + vacuum folder. Note that the free folder is overwritten, which is what we want because
# we've equilibrated the ligand and ligand+protein separately.
print("Free..")
BSS.FreeEnergy.Solvation(
                    system_free, 
                    freenrg_protocol, 
                    engine=f"{engine_query}",
                    work_dir=f"outputs/{engine_query}/{sys.argv[1]}~{sys.argv[2]}"
)













