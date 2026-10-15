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
                return False, "No opening GS for GE/ST envelope"
            
            #closing the GE before closing the SE/ST
            elif st_found:
                return False, "No closing SE for ST/SE v"

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