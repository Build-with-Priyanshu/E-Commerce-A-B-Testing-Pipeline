import scipy as sp


def proportions_z_test(p1, p2, n1, n2):
    if n1 <= 0 or n2 <= 0:
        raise ValueError("Both groups must contain observations.")
    if not (0 <= p1 <= 1 and 0 <= p2 <= 1):
        raise ValueError("Both proportions must be between 0 and 1.")
    standard_error = (p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) ** 0.5
    if standard_error == 0:
        return 1.0 if p1 == p2 else 0.0
    z = (p1 - p2) / standard_error
    # two-sided P-value
    return sp.stats.norm.sf(abs(z)) * 2

def check_srm(num_a, num_b, expected_ratio_a=0.5):
    """
    Checks for Sample Ratio Mismatch (SRM) using a Chi-Square test.
    
    Args:
        num_a (int): Number of unique users in Group A.
        num_b (int): Number of unique users in Group B.
        expected_ratio_a (float): The intended split for Group A (e.g., 0.5 for 50/50).
        
    Returns: p-value.
    """
    if num_a < 0 or num_b < 0 or num_a + num_b == 0:
        raise ValueError("Assignment counts must be non-negative and not both zero.")
    if not 0 < expected_ratio_a < 1:
        raise ValueError("Expected group-A ratio must be between 0 and 1.")
    total_num = num_a + num_b
    # Calculate expected counts based on the total num users
    expected_a = total_num * expected_ratio_a
    expected_b = total_num * (1 - expected_ratio_a)
    observed = [num_a, num_b]
    expected = [expected_a, expected_b]
    
    chi2_stat, p_value = sp.stats.chisquare(f_obs=observed, f_exp=expected)
    
    return p_value
