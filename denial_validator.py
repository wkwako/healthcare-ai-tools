from pathlib import Path
from decimal import Decimal

def get_segments(text):
    if "~" in text:
        raw_segments = text.split("~")
    else:
        raw_segments = text.splitlines()

    segments = []
    for s in raw_segments:
        line = s.strip()
        if line:
            segments.append(line)

    return segments

def create_info_dict(segments):
    info_dict = {}
    for segment in segments:
        elements = segment.split("*")
        info_dict[elements[0]] = elements

    return info_dict

def get_element(name, location, info_dict):
    if not info_dict:
        return None

    return info_dict[name][location]

def structure_check(segments):
    if not segments:
        return False, "Empty file"
    gs_found = False
    st_found = False
    st_count = 0

    if segments[0][:3] != "ISA" or segments[-1][:3] != "IEA":
        return False, "ISA/IEA structural issues"

    for line in segments:

        #increment count to track segments between SE and ST
        if st_found:
            st_count += 1
        
        #GS/GE check
        marker = line.split("*")[0]
        if marker == "GS":
            #found a GS but we needed an ST to close the SE first
            if st_found:
                return False, "No closing SE for SE/ST envelope"
            
            #found another GS without closing the first
            elif gs_found:
                return False, "No closing GE for GS/GE envelope"
            else:
                gs_found = True

        elif marker == "GE":
            #didn't find a GS, nothing to close
            if not gs_found:
                return False, "No opening GS for GS/GE envelope"
            
            #closing the GE before closing the SE/ST
            elif st_found:
                return False, "No closing SE for ST/SE envelope"

            #close the GE/ST by setting sg_found to False
            else:
                gs_found = False

        #ST/SE check
        elif marker == "ST":
            #ST found before opening GS 
            if not gs_found:
                return False, "No opening GS before opening SE"

            #found another ST before closing the first
            if st_found:
                return False, "No closing SE for ST/SE envelope"

            #open the ST/SE pair
            else:
                st_count = 1
                st_found = True

        elif marker == "SE":
            #found an SE before finding an ST
            if not st_found:
                return False, "No opening ST for ST/SE envelope"

            #found a closing SE that isn't enclosed in GS/GE envelope
            if not gs_found:
                return False, "No opening GS before closing ST/SE envelope"

            else:
                expected = int(line.split("*")[1])
                if st_count != int(expected):
                    return False, f"SE/ST count error. Got {st_count}, expected {expected}"

                else:
                    st_found = False

    if st_found:
        return False, "No closing SE for ST/SE envelope"
    if gs_found:
        return False, "No closing GE for GS/GE envelope"

    return True, ""

def balance_check(segments):
    i = 0
    while i < len(segments):
        line = segments[i]
        elements = line.split("*")

        if elements[0] == "ST":
            bpr_amount = 0
            paid_total = 0
            plb_total = 0

        elif elements[0] == "BPR":
            if len(elements) >= 3:
                bpr_amount = Decimal(elements[2])
            
        elif elements[0] == "CLP":
            #payment found
            if len(elements) < 5:
                return False, f"Incomplete CLP segment at line {i}"
            
            billed = Decimal(elements[3])
            paid = Decimal(elements[4])
            paid_total += paid
            adjustments = []

            #start looking for line-level payments
            j = 1   
            new_line = segments[i+j]
            new_elements = new_line.split("*")
            while new_elements[0] == "CAS":
                for k in range(3, len(new_elements), 3):
                    adjustments.append(Decimal(new_elements[k]))
                j += 1
                new_line = segments[i+j]
                new_elements = new_line.split("*")

            if billed - sum(adjustments) != paid:
                return False, f"Sum of payments does not equal paid for CLP at line {i}"

            i += j - 1

        elif elements[0] == "PLB":
            plb_adjustments = []
            for k in range(4, len(elements), 2):
                plb_adjustments.append(Decimal(elements[k]))
            plb_total += sum(plb_adjustments)

        elif elements[0] == "SE":
            if paid_total - plb_total != bpr_amount:
                return False, "PLB total does not match BPR02 total"
        i += 1

    return True, ""

# path = Path(__file__).parent / "tests" / "sample_835s" / "partial_payments.835"
# text = path.read_text()
# segments = get_segments(text)
# print (balance_check(segments))