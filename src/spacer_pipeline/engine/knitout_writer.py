"""
COMP116 HW5 Part 2 - Knitout Writer Class
Name: Solution
Date: 04/05/2026

This file contains the Python class KnitoutWriter for generating knitout files.

Knitout is a file format for specifying knitting machine instructions.
A knitout file starts with a magic string and headers, followed by
a sequence of operations (knit, tuck, xfer, etc.).
Reference: https://textiles-lab.github.io/knitout/knitout.html
"""

class KnitoutWriter:
    """
    A writer for generating knitout-formatted knitting machine instructions.

    The writer manages:
    - A list of available carrier names (set at construction)
    - A set of currently active carriers (carriers that have been brought in)
    - A list of knitout instructions (built up by calling methods)
    - Custom headers (metadata about the file)
    - The current racking value

    Example usage:
        w = KnitoutWriter(carriers=[1, 2, 3])
        w.add_header("Machine", "SWGN2")
        w.inhook(1)
        w.knit("+", "f0", 1)
        w.outhook(1)
        w.write("output.k")
    """
    # Add any class variables here if you think there are any
    MAGIC_STRING = ";!knitout-2"
    VALID_DIRECTIONS = ["+", "-"]

    def __init__(self, carriers=None):
        """Initialize the KnitoutWriter.

        Parameters:
        - carriers: a list of carrier names (e.g., [1, 2, 3]).
                    Defaults to an empty list if not provided.

        Should initialize:
        - self.carriers: the list of available carrier names
        - self.instructions: an empty list (will hold instruction strings)
        - self.active_carriers: an empty set (tracks which carriers are in use)
        - self.headers: an empty list (will hold header strings)
        - self.racking: 0 (the current racking offset)
        """
        self.carriers = [] if carriers is None else carriers
        self.instructions = []
        self.active_carriers = set()
        self.headers = []
        self.racking = 0

    # ================================================================
    # Header Management
    # ================================================================

    def add_header(self, name, value):
        """Add a header to the knitout file.

        Headers are metadata lines that appear at the top of the file,
        formatted as ";;Name: Value".

        Parameters:
        - name: header name (string, e.g., "Machine", "Gauge", "Position")
        - value: header value (string, e.g., "SWGN2", "15", "Center")

        Should append the formatted header string to self.headers.
        """
        self.headers.append(f";;{name.title()}: {value}")

    # ================================================================
    # Carrier Operations
    # ================================================================

    def inhook(self, carrier):
        """Bring a yarn carrier into action using the yarn inserting hook.

        Parameters:
        - carrier: the carrier name to bring in

        Should:
        - Validate that the carrier is in self.carriers (raise error if not)
        - Validate that the carrier is not already active (raise error if so)
        - Add the carrier to self.active_carriers
        - Append "inhook {carrier}" to self.instructions
        """
        assert carrier in self.carriers, f"Invalid carrier: {carrier}"
        assert carrier not in self.active_carriers, f"Cannot inhook a currently active carrier: {carrier}"
        self.active_carriers.add(carrier)
        self.instructions.append(f"inhook {carrier}")

    def releasehook(self, carrier):
        """Release the yarn inserting hook for a carrier.

        The carrier remains active after release.

        Parameters:
        - carrier: the carrier name to release

        Should:
        - Validate that the carrier is currently active (raise error if not)
        - Append "releasehook {carrier}" to self.instructions
        """
        assert carrier in self.active_carriers, f"Cannot releasehook an inactive carrier: {carrier}"
        self.instructions.append(f"releasehook {carrier}")

    def outhook(self, carrier):
        """Take a yarn carrier out of action using the yarn inserting hook.

        Parameters:
        - carrier: the carrier name to take out

        Should:
        - Validate that the carrier is currently active (raise error if not)
        - Remove the carrier from self.active_carriers
        - Append "outhook {carrier}" to self.instructions
        """
        assert carrier in self.active_carriers, f"Cannot outhook an inactive carrier: {carrier}"
        self.active_carriers.remove(carrier)
        self.instructions.append(f"outhook {carrier}")

    # ================================================================
    # Knitting Operations
    # ================================================================

    def _validate_direction(self, direction):
        """
        Validate that direction is '+' or '-'.

        Parameters:
        - direction: the direction string to validate

        Should raise an error if direction is not '+' or '-'.
        This is a helper method used by the knitting operations.
        """
        assert direction in KnitoutWriter.VALID_DIRECTIONS, f"Invalid knitting direction: {direction}"

    def _validate_active_carrier(self, carrier):
        """
        Validate that a carrier is currently active.

        Parameters:
        - carrier: the carrier name to check

        Should raise an error if the carrier is not in self.active_carriers.
        This is a helper method used by the knitting operations.
        """
        assert carrier in self.active_carriers, f"Inactive carrier: {carrier}; have you inhooked the carrier?"

    def knit(self, direction, bed_needle, carrier):
        """Knit a stitch: pull a loop of yarn through any loops on the needle.

        Parameters:
        - direction: '+' (left to right) or '-' (right to left)
        - bed_needle: string like "f5" (front needle 5) or "b3" (back needle 3)
        - carrier: the carrier to use (must be active)

        Should:
        - Validate direction and carrier
        - Append "knit {direction} {bed_needle} {carrier}" to self.instructions
        """
        self._validate_direction(direction)
        self._validate_active_carrier(carrier)
        self.instructions.append(f"knit {direction} {bed_needle} {carrier}")

    def tuck(self, direction, bed_needle, carrier):
        """Tuck: add a loop to the needle without dropping existing loops.

        Parameters:
        - direction: '+' or '-'
        - bed_needle: string like "f5" or "b3"
        - carrier: the carrier to use (must be active)

        Should:
        - Validate direction and carrier
        - Append "tuck {direction} {bed_needle} {carrier}" to self.instructions
        """
        self._validate_direction(direction)
        self._validate_active_carrier(carrier)
        self.instructions.append(f"tuck {direction} {bed_needle} {carrier}")

    def miss(self, direction, bed_needle, carrier):
        """Miss: move the carrier past a needle without forming a loop.

        Parameters:
        - direction: '+' or '-'
        - bed_needle: string like "f5" or "b3"
        - carrier: the carrier to use (must be active)

        Should:
        - Validate direction and carrier
        - Append "miss {direction} {bed_needle} {carrier}" to self.instructions
        """
        self._validate_direction(direction)
        self._validate_active_carrier(carrier)
        self.instructions.append(f"miss {direction} {bed_needle} {carrier}")

    def split(self, direction, from_bed_needle, to_bed_needle, carrier):
        """Split: transfer loops and knit at the same time.

        Parameters:
        - direction: '+' or '-'
        - from_bed_needle: source needle string (e.g., "f5")
        - to_bed_needle: target needle string (e.g., "b5")
        - carrier: the carrier to use (must be active)

        Should:
        - Validate direction and carrier
        - Append "split {direction} {from_bed_needle} {to_bed_needle} {carrier}"
          to self.instructions
        """
        self._validate_direction(direction)
        self._validate_active_carrier(carrier)
        self.instructions.append(f"split {direction} {from_bed_needle} {to_bed_needle} {carrier}")

    def drop(self, bed_needle):
        """Drop: release all loops from a needle (no carrier needed).

        Parameters:
        - bed_needle: string like "f5" or "b3"

        Should append "drop {bed_needle}" to self.instructions.
        """
        self.instructions.append(f"drop {bed_needle}")

    def xfer(self, from_bed_needle, to_bed_needle):
        """Transfer: move loops from one needle to another (no carrier needed).

        Parameters:
        - from_bed_needle: source needle string (e.g., "f5")
        - to_bed_needle: target needle string (e.g., "b5")

        Should:
        - Validate the two needles are on different needle beds
        - Validate the two needles meet at the current racking value
        - Append "xfer {from_bed_needle} {to_bed_needle}" to self.instructions.
        """
        from_needle_bed = from_bed_needle[0]
        to_needle_bed = to_bed_needle[0]
        assert from_needle_bed != to_needle_bed,\
            "Transfer cannot be performed on two needles " +\
            f"({from_bed_needle}, {to_bed_needle}) on the same bed"
        from_needle_index = int(from_bed_needle[1:])
        to_needle_index = int(to_bed_needle[1:])
        front_bed_index = from_needle_index if from_needle_bed == "f" else to_needle_index
        back_bed_index = from_needle_index if from_needle_bed == "b" else to_needle_index
        assert front_bed_index == back_bed_index + self.racking,\
            "Transfer cannot be performed on two needles" +\
            f"({from_bed_needle}, {to_bed_needle}) at racking {self.racking}"
        self.instructions.append(f"xfer {from_bed_needle} {to_bed_needle}")

    def rack(self, value):
        """Set the racking position (offset between front and back beds).

        Parameters:
        - value: the racking value (number)

        Should:
        - Update self.racking to the new value
        - Append "rack {value}" to self.instructions
        """
        self.racking = value
        self.instructions.append(f"rack {value}")

    # ================================================================
    # Comments
    # ================================================================

    def comment(self, text):
        """Add a comment to the instruction list.

        Parameters:
        - text: the comment text (will be prefixed with ';')

        Should append ";{text}" to self.instructions.
        """
        self.instructions.append(f";{text}")

    # ================================================================
    # Output
    # ================================================================

    def write(self, filename=None):
        """Generate the complete knitout file content and optionally write to file.

        The output format is:
            ;!knitout-2
            ;;Carriers: {carrier1} {carrier2} ...
            ;;Header1: Value1
            ;;Header2: Value2
            {instruction1}
            {instruction2}
            ...

        Parameters:
        - filename: if provided, write the output to this file.
                    If None, just return the string.

        Returns:
        - The complete knitout file content as a string.
        """
        knitout_lines = [KnitoutWriter.MAGIC_STRING]
        carriers_str = [str(carrier) for carrier in self.carriers]
        knitout_lines.append(f";;Carriers: {' '.join(carriers_str)}")
        knitout_lines.extend(self.headers)
        knitout_lines.extend(self.instructions)
        knitout_file_content = "\n".join(knitout_lines)
        if filename is not None:
            with open(filename, "w") as outfile:
                outfile.write(knitout_file_content)
        return knitout_file_content
